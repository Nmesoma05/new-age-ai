"""The outbound HTTP client: allowlist, retries, no blind retries of writes, breaker, size cap, call log."""
import httpx
import pytest
from sqlalchemy import select

from app.core.db import transaction
from app.integrations import http as ihttp
from app.integrations.http import (
    CallContext,
    IntegrationError,
    OutcomeUnknown,
    ProviderLimits,
)
from app.models import IntegrationCall

L = ProviderLimits(hosts=frozenset({"api.example.com"}), rate_per_sec=100, burst=100)


async def _call(method="GET", url="https://api.example.com/v1/x?token=SECRET", **kw):
    async with transaction(None, context="system") as s:
        return await ihttp.request(CallContext(s, "p", "op"), L, method, url, **kw)


async def _log():
    async with transaction(None, context="system") as s:
        return (await s.execute(select(IntegrationCall).order_by(IntegrationCall.created_at))).scalars().all()


def _seq(*responses):
    it = iter(responses)

    def h(req):
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return r
    return h


@pytest.fixture
def transport(fake):  # reuse fake's sleep patch + settings; swap the transport per test
    def _use(handler):
        ihttp.set_transport(httpx.MockTransport(handler))
    return _use


async def test_retry_get_then_success_and_log_has_no_secrets(transport, fake):
    transport(_seq(httpx.Response(503), httpx.Response(429, headers={"retry-after": "7"}), httpx.Response(200, json={})))
    r = await _call()
    assert r.status_code == 200
    assert fake.slept[-1] == 7.0  # Retry-After honoured
    rows = await _log()
    assert [x.outcome for x in rows] == ["server_error", "rate_limited", "retried"]
    assert all(x.path == "/v1/x" and "SECRET" not in (x.path + x.host) for x in rows)


async def test_retry_after_is_capped(transport, fake):
    transport(_seq(httpx.Response(429, headers={"retry-after": "9999"}), httpx.Response(200)))
    await _call()
    assert fake.slept[-1] == L.max_retry_after


async def test_post_is_never_retried(transport):
    calls = []

    def h(req):
        calls.append(req)
        return httpx.Response(503)
    transport(h)
    with pytest.raises(IntegrationError) as e:
        await _call("POST", json_body={"text": "hi"})
    assert e.value.code == "provider_error" and len(calls) == 1


async def test_post_timeout_is_outcome_unknown_but_connect_error_is_not(transport):
    transport(_seq(httpx.ReadTimeout("slow")))
    with pytest.raises(OutcomeUnknown):
        await _call("POST", json_body={})
    transport(_seq(httpx.ConnectError("down")))
    with pytest.raises(IntegrationError) as e:
        await _call("POST", json_body={})
    assert e.value.code == "network_error" and "nothing was sent" in e.value.message


async def test_host_allowlist_and_https(transport):
    transport(_seq())
    for url in ("https://evil.example.com/x", "http://api.example.com/x", "https://api.example.com.evil.io/x"):
        with pytest.raises(IntegrationError) as e:
            await _call(url=url)
        assert e.value.code == "host_not_allowed"
    assert {x.outcome for x in await _log()} == {"blocked"}


async def test_auth_errors_and_size_cap(transport):
    transport(_seq(httpx.Response(401)))
    with pytest.raises(ihttp.AuthExpired):
        await _call()
    transport(_seq(httpx.Response(403)))
    with pytest.raises(IntegrationError) as e:
        await _call()
    assert e.value.code == "permission_denied"
    transport(_seq(httpx.Response(200, content=b"x" * (ihttp.MAX_BYTES + 1))))
    with pytest.raises(IntegrationError) as e:
        await _call()
    assert e.value.code == "response_too_large"


async def test_circuit_breaker_opens(transport):
    transport(lambda req: httpx.Response(500))
    for _ in range(2):  # 3 attempts each -> 6 failures >= threshold 5
        with pytest.raises(IntegrationError):
            await _call()
    with pytest.raises(IntegrationError) as e:
        await _call()
    assert e.value.code == "provider_unavailable"
    assert (await _log())[-1].outcome == "circuit_open"


async def test_outbound_switch(monkeypatch):
    ihttp.set_transport(None)
    with pytest.raises(IntegrationError) as e:
        await _call()
    assert e.value.code == "outbound_disabled"

