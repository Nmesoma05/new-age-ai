"""The only way the backend talks to external providers.

Guarantees, per call:
- Host allowlist per provider (no arbitrary URLs: SSRF protection) and HTTPS only.
- Timeouts (connect 5s, total 20s by default) and a response size cap.
- Retries ONLY for idempotent requests (GET, or a write the provider makes idempotent with a key we send), on
  network errors, 429 and 5xx, with exponential backoff + jitter, honouring Retry-After up to a ceiling.
  A non-idempotent write is never retried automatically: if its outcome is unclear we raise OutcomeUnknown so the
  caller records that, instead of risking a duplicate post, message or charge.
- A per-provider token-bucket rate limiter and a circuit breaker (opens after repeated failures).
- Every attempt is logged to integration_calls (method, host, path without query, status, outcome, latency).
  Tokens, query strings and bodies are never logged.

Rate limiter and breaker state are in-process. With several API instances, move them to Redis (documented).
"""
from __future__ import annotations

import asyncio
import json
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import transaction
from app.models import IntegrationCall

MAX_BYTES = 5 * 1024 * 1024
RETRY_STATUSES = {429, 500, 502, 503, 504}


class IntegrationError(Exception):
    """A provider call failed. `code` is safe to show; `retryable` tells callers whether trying later may help."""

    def __init__(self, code: str, message: str, *, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.code, self.message, self.status, self.retryable = code, message, status, retryable


class AuthExpired(IntegrationError):
    def __init__(self, message: str = "The connection needs to be renewed. Reconnect the account."):
        super().__init__("needs_reauth", message, status=401)


class OutcomeUnknown(IntegrationError):
    """A write may or may not have happened (e.g. timeout after sending). Never report success or retry blindly."""

    def __init__(self, message: str = "We couldn't confirm whether the provider completed this. Check the account "
                                      "before trying again."):
        super().__init__("outcome_unknown", message)


@dataclass
class _Bucket:
    rate_per_sec: float
    capacity: float
    tokens: float = 0.0
    updated: float = field(default_factory=time.monotonic)

    def take(self) -> float:
        """Take one token; return seconds to wait first (0 if available)."""
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate_per_sec)
        self.updated = now
        if self.tokens >= 1:
            self.tokens -= 1
            return 0.0
        wait = (1 - self.tokens) / self.rate_per_sec
        self.tokens = 0
        self.updated = now + wait
        return wait


@dataclass
class _Breaker:
    threshold: int = 5
    cooldown: float = 60.0
    failures: int = 0
    opened_at: float | None = None

    def allow(self) -> bool:
        if self.opened_at is None:
            return True
        if time.monotonic() - self.opened_at >= self.cooldown:  # half-open: let one try through
            self.opened_at = None
            self.failures = self.threshold - 1
            return True
        return False

    def record(self, ok: bool) -> None:
        if ok:
            self.failures, self.opened_at = 0, None
        else:
            self.failures += 1
            if self.failures >= self.threshold:
                self.opened_at = time.monotonic()


@dataclass(frozen=True)
class ProviderLimits:
    hosts: frozenset[str]
    rate_per_sec: float = 2.0
    burst: float = 4.0
    max_attempts: int = 3
    base_delay: float = 0.5
    max_retry_after: float = 30.0


_buckets: dict[str, _Bucket] = {}
_breakers: dict[str, _Breaker] = {}
_transport: httpx.AsyncBaseTransport | None = None  # tests inject a MockTransport here
_sleep = asyncio.sleep  # tests replace this to skip backoff waits


def set_transport(t: httpx.AsyncBaseTransport | None) -> None:
    global _transport
    _transport = t
    _buckets.clear()
    _breakers.clear()


def _retry_after(resp: httpx.Response, ceiling: float) -> float | None:
    v = resp.headers.get("retry-after")
    if not v:
        return None
    try:
        secs = float(v)
    except ValueError:
        try:
            secs = (parsedate_to_datetime(v) - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError):
            return None
    return max(0.0, min(secs, ceiling))


@dataclass
class CallContext:
    session: AsyncSession
    provider: str
    operation: str
    org_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None
    integration_id: uuid.UUID | None = None


async def _log(ctx: CallContext, method: str, url: str, status: int | None, outcome: str, attempt: int,
               ms: int | None) -> None:
    """Own committed transaction: a failed call must stay in the log even when the request then rolls back."""
    parts = urlsplit(url)
    async with transaction(None, context="system") as s:
        s.add(IntegrationCall(integration_id=ctx.integration_id, org_id=ctx.org_id,
                                        workspace_id=ctx.workspace_id, provider=ctx.provider,
                                        operation=ctx.operation[:80], method=method, host=parts.hostname or "",
                                        path=parts.path[:300], status_code=status, outcome=outcome, attempt=attempt,
                                        latency_ms=ms))


def _outcome(status: int) -> str:
    if status in (401, 403):
        return "auth_error"
    if status == 429:
        return "rate_limited"
    if status >= 500:
        return "server_error"
    return "client_error" if status >= 400 else "ok"


async def request(ctx: CallContext, limits: ProviderLimits, method: str, url: str, *, idempotent: bool | None = None,
                  headers: dict | None = None, params: dict | None = None, data: dict | None = None,
                  json_body: Any = None, timeout: float = 20.0) -> httpx.Response:
    """Send one logical request with the guarantees in the module docstring. Returns a 2xx response or raises."""
    if not get_settings().outbound_http_enabled and _transport is None:
        raise IntegrationError("outbound_disabled", "External connections are switched off on this server.")
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in limits.hosts:
        await _log(ctx, method, url, None, "blocked", 1, None)
        raise IntegrationError("host_not_allowed", "That address isn't allowed for this integration.")
    idempotent = method in ("GET", "HEAD") if idempotent is None else idempotent
    bucket = _buckets.setdefault(ctx.provider, _Bucket(limits.rate_per_sec, limits.burst, tokens=limits.burst))
    breaker = _breakers.setdefault(ctx.provider, _Breaker())
    attempts = limits.max_attempts if idempotent else 1
    async with httpx.AsyncClient(transport=_transport, timeout=httpx.Timeout(timeout, connect=5.0),
                                 follow_redirects=False) as client:
        for attempt in range(1, attempts + 1):
            if not breaker.allow():
                await _log(ctx, method, url, None, "circuit_open", attempt, None)
                raise IntegrationError("provider_unavailable", "The provider is failing right now. Try again in a "
                                       "minute.", retryable=True)
            wait = bucket.take()
            if wait:
                await _sleep(wait)
            t0 = time.monotonic()
            try:
                resp = await client.request(method, url, headers=headers, params=params, data=data, json=json_body)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                ms = int((time.monotonic() - t0) * 1000)
                await _log(ctx, method, url, None, "network_error", attempt, ms)
                breaker.record(False)
                if not idempotent:
                    # The request may have reached the provider. Don't guess, don't retry.
                    if isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout)):
                        raise IntegrationError("network_error", "Couldn't reach the provider; nothing was sent.",
                                               retryable=True) from e
                    raise OutcomeUnknown() from e
                if attempt == attempts:
                    raise IntegrationError("network_error", "Couldn't reach the provider.", retryable=True) from e
                await _sleep(limits.base_delay * 2 ** (attempt - 1) * (0.5 + random.random()))
                continue
            ms = int((time.monotonic() - t0) * 1000)
            if int(resp.headers.get("content-length") or 0) > MAX_BYTES or len(resp.content) > MAX_BYTES:
                await _log(ctx, method, url, resp.status_code, "client_error", attempt, ms)
                raise IntegrationError("response_too_large", "The provider sent more data than allowed.")
            if resp.status_code < 400:
                await _log(ctx, method, url, resp.status_code, "ok" if attempt == 1 else "retried", attempt, ms)
                breaker.record(True)
                return resp
            outcome = _outcome(resp.status_code)
            await _log(ctx, method, url, resp.status_code, outcome, attempt, ms)
            if resp.status_code in RETRY_STATUSES:
                if resp.status_code != 429:  # rate limiting isn't a provider failure
                    breaker.record(False)
                if idempotent and attempt < attempts:
                    delay = _retry_after(resp, limits.max_retry_after)
                    await _sleep(delay if delay is not None
                                        else limits.base_delay * 2 ** (attempt - 1) * (0.5 + random.random()))
                    continue
                if resp.status_code == 429:
                    raise IntegrationError("rate_limited", "The provider's rate limit was reached. Try later.",
                                           status=429, retryable=True)
                raise IntegrationError("provider_error", "The provider returned an error. Try later.",
                                       status=resp.status_code, retryable=True)
            breaker.record(True)  # 4xx means the provider is up
            if resp.status_code in (401, 403) and outcome == "auth_error":
                if resp.status_code == 401:
                    raise AuthExpired()
                raise IntegrationError("permission_denied", "The connected account doesn't allow this. Check its "
                                       "permissions.", status=403)
            raise IntegrationError("bad_request", f"The provider rejected the request ({resp.status_code}).",
                                   status=resp.status_code)
    raise IntegrationError("network_error", "Couldn't reach the provider.", retryable=True)  # pragma: no cover


def json_of(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError) as e:
        raise IntegrationError("bad_response", "The provider sent something we couldn't read.") from e
