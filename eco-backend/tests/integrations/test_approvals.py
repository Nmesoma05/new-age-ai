"""Approval gate for external writes: nothing counts as done without provider proof."""
import pytest

from app.ai import actions
from app.integrations.http import IntegrationError, OutcomeUnknown
from tests.ai.test_actions_memory_api import _propose, connect_test_social


class Ex:
    kind, provider = "publish_post", "test_social"

    def __init__(self, behaviour):
        self.behaviour, self.calls = behaviour, 0

    async def execute(self, action, integration, key):
        self.calls += 1
        b = self.behaviour
        if isinstance(b, Exception):
            raise b
        return b


@pytest.fixture
def use():
    def _u(behaviour):
        ex = Ex(behaviour)
        actions.register(ex)
        return ex
    yield _u
    actions.unregister("publish_post")


def test_no_write_executors_in_production():
    import app.main  # noqa: F401  (importing the app must not register any)
    assert actions.EXECUTORS == {}


@pytest.mark.parametrize("behaviour,error", [
    (OutcomeUnknown(), "outcome_unknown"),
    (IntegrationError("rate_limited", "Try later", status=429), "rate_limited"),
    ({"url": "https://social.example/p/1"}, "no_confirmation"),  # a URL alone isn't proof from the provider
    (None, "no_confirmation"),
])
async def test_unconfirmed_outcomes_are_failures(client, signup, make_workspace, provider, use, behaviour, error):
    a = await signup()
    ws = await make_workspace(a)
    await connect_test_social(ws, a.user_id)
    ex = use(behaviour)
    aid = await _propose(client, provider, a, ws)
    r = await client.post(f"/v1/workspaces/{ws}/actions/{aid}/approve", headers=a.h)
    assert r.status_code == 200
    assert r.json()["status"] == "failed" and r.json()["result"]["error"] == error and r.json()["executed_at"] is None
    again = await client.post(f"/v1/workspaces/{ws}/actions/{aid}/approve", headers=a.h)
    assert again.status_code == 409 and ex.calls == 1  # never retried automatically


async def test_needs_reauth_or_revoked_connection_blocks(client, signup, make_workspace, provider, use):
    a = await signup()
    ws = await make_workspace(a)
    for status in ("needs_reauth", "revoked"):
        await connect_test_social(ws, a.user_id, status=status)
    ex = use({"provider_ref": "x"})
    aid = await _propose(client, provider, a, ws)
    r = await client.post(f"/v1/workspaces/{ws}/actions/{aid}/approve", headers=a.h)
    assert r.status_code == 409 and r.json()["code"] == "no_connection" and ex.calls == 0
    listed = (await client.get(f"/v1/workspaces/{ws}/actions?status=awaiting_approval", headers=a.h)).json()["data"]
    assert [x["id"] for x in listed] == [aid]  # still waiting, nothing claimed


async def test_connection_in_another_workspace_does_not_count(client, signup, make_workspace, provider, use,
                                                             activate_plan):
    a = await signup()
    await activate_plan(a.org_id, "pro")
    ws, other = await make_workspace(a, "One"), await make_workspace(a, "Two")
    await connect_test_social(other, a.user_id)
    use({"provider_ref": "x"})
    aid = await _propose(client, provider, a, ws)
    r = await client.post(f"/v1/workspaces/{ws}/actions/{aid}/approve", headers=a.h)
    assert r.status_code == 409 and r.json()["code"] == "no_connection"
