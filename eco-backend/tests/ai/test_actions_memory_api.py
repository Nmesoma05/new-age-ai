"""Approval workflow for external actions, and the memory API."""

import pytest

from app.ai import actions
from tests.ai.helpers import conversation, reply, route, send
from tests.ai.scripted import call


class RecordingExecutor:
    """Test-only. Production has no write executors registered."""
    provider = "test_social"

    def __init__(self, kind, fail=False):
        self.kind, self.fail, self.done = kind, fail, []

    async def execute(self, action, integration, idempotency_key):
        if self.fail:
            raise RuntimeError("provider down")
        assert idempotency_key == action.id and integration.provider == "test_social"
        self.done.append(action.id)
        return {"provider_ref": "p_1", "url": "https://social.example/p/1"}


async def connect_test_social(ws, user_id, status="connected"):
    """Insert a connected (fake) account row for the test executor."""
    import uuid as _u

    from app.core.crypto import encrypt_json
    from app.core.db import transaction
    from app.models import Integration, Workspace
    async with transaction(None, context="system") as s:
        w = await s.get(Workspace, _u.UUID(str(ws)))
        s.add(Integration(org_id=w.org_id, workspace_id=w.id, provider="test_social", status=status,
                          encrypted_credentials=encrypt_json({"access_token": "t"}), created_by=user_id))


@pytest.fixture
def executor():
    ex = RecordingExecutor("publish_post")
    actions.register(ex)
    yield ex
    actions.unregister("publish_post")


async def _agency(client, signup, activate_plan):
    owner, editor = await signup("Owner"), await signup("Editor")
    org = (await client.post("/v1/orgs", headers=owner.h, json={"name": "Agency"})).json()["id"]
    await activate_plan(org, "team")
    await client.post(f"/v1/orgs/{org}/products", headers=owner.h, json={"product": "creator"})
    await client.post(f"/v1/orgs/{org}/members", headers=owner.h, json={"email": editor.email, "role": "member"})
    ws = (await client.post(f"/v1/orgs/{org}/workspaces", headers=owner.h, json={"name": "C", "product": "creator"})).json()["id"]
    await client.post(f"/v1/workspaces/{ws}/members", headers=owner.h, json={"user_id": str(editor.user_id), "role": "editor"})
    return owner, editor, ws


async def _propose(client, provider, acct, ws, kind="publish_post", **extra):
    args = {"kind": kind, "title": "Launch post", "content": "We're live!", "platform": "instagram", "recipient": None,
            "amount": None, "currency": None, **extra}
    provider.on("router", route("creator.assistant"))
    provider.on("creator.assistant", call("propose_external_action", args), reply("Queued for approval."))
    conv = await conversation(client, acct, ws)
    r = await send(client, acct, ws, conv, "post the launch announcement")
    assert r.status_code == 201, r.text
    return r.json()["run"]["pending_actions"][0]["id"]


async def test_editor_proposes_admin_approves_and_it_executes_once(client, signup, activate_plan, provider, executor,
                                                                 owner_db):
    owner, editor, ws = await _agency(client, signup, activate_plan)
    aid = await _propose(client, provider, editor, ws)
    r = await client.post(f"/v1/workspaces/{ws}/actions/{aid}/approve", headers=owner.h)
    assert r.status_code == 409 and r.json()["code"] == "no_connection" and executor.done == []
    await connect_test_social(ws, owner.user_id)
    listed = (await client.get(f"/v1/workspaces/{ws}/actions?status=awaiting_approval", headers=editor.h)).json()["data"]
    assert [x["id"] for x in listed] == [aid] and listed[0]["payload"]["content"] == "We're live!"
    r = await client.post(f"/v1/workspaces/{ws}/actions/{aid}/approve", headers=editor.h)
    assert r.status_code == 403 and executor.done == []
    r = await client.post(f"/v1/workspaces/{ws}/actions/{aid}/approve", headers=owner.h)
    assert r.status_code == 200 and r.json()["status"] == "executed" and r.json()["result"]["url"]
    assert r.json()["decided_by"] == str(owner.user_id)
    again = await client.post(f"/v1/workspaces/{ws}/actions/{aid}/approve", headers=owner.h)
    assert again.status_code == 409 and len(executor.done) == 1
    audit = [x[0] for x in owner_db.execute("SELECT action FROM audit_events ORDER BY id").fetchall()]
    assert audit.index("ai.action_proposed") < audit.index("ai.action_approved") < audit.index("ai.action_executed")


async def test_reject_expire_and_executor_failure(client, signup, make_workspace, provider, owner_db):
    a = await signup("Ada")
    ws = await make_workspace(a)
    aid = await _propose(client, provider, a, ws)
    r = await client.post(f"/v1/workspaces/{ws}/actions/{aid}/reject", headers=a.h, json={"reason": "Wrong tone"})
    assert r.json()["status"] == "rejected" and r.json()["result"] == {"reason": "Wrong tone"}
    aid2 = await _propose(client, provider, a, ws)
    owner_db.execute("UPDATE pending_actions SET expires_at = now() - interval '1 minute' WHERE id = %s", (aid2,))
    r = await client.post(f"/v1/workspaces/{ws}/actions/{aid2}/reject", headers=a.h)
    assert r.status_code == 409 and r.json()["code"] == "action_expired"
    assert owner_db.execute("SELECT status FROM pending_actions WHERE id = %s", (aid2,)).fetchone() == ("expired",)
    ex = RecordingExecutor("publish_post", fail=True)
    actions.register(ex)
    await connect_test_social(ws, a.user_id)
    try:
        aid3 = await _propose(client, provider, a, ws)
        r = await client.post(f"/v1/workspaces/{ws}/actions/{aid3}/approve", headers=a.h)
        assert r.json()["status"] == "failed" and r.json()["result"] == {"error": "execution_failed"}
    finally:
        actions.unregister("publish_post")


async def test_spending_needs_org_admin(client, signup, activate_plan, provider):
    owner, editor, ws = await _agency(client, signup, activate_plan)
    # promote the editor to workspace admin: still not an org owner/admin
    await client.patch(f"/v1/workspaces/{ws}/members/{editor.user_id}", headers=owner.h, json={"role": "admin"})
    aid = await _propose(client, provider, editor, ws, kind="spend_money", platform=None, amount=15000, currency="NGN",
                         content="Boost the launch post")
    r = await client.post(f"/v1/workspaces/{ws}/actions/{aid}/approve", headers=editor.h)
    assert r.status_code == 403 and "organisation owner or admin" in r.json()["detail"]
    r = await client.post(f"/v1/workspaces/{ws}/actions/{aid}/reject", headers=owner.h)
    assert r.json()["status"] == "rejected"


async def test_actions_and_memory_invisible_to_other_tenants(client, signup, make_workspace, provider):
    a, b = await signup("Ada"), await signup("Bola")
    ws, ws_b = await make_workspace(a), await make_workspace(b)
    aid = await _propose(client, provider, a, ws)
    assert (await client.post(f"/v1/workspaces/{ws_b}/actions/{aid}/approve", headers=b.h)).status_code == 404
    assert (await client.post(f"/v1/workspaces/{ws}/actions/{aid}/approve", headers=b.h)).status_code == 404
    m = (await client.post(f"/v1/workspaces/{ws}/memory", headers=a.h, json={"content": "Tone: warm"})).json()
    assert (await client.delete(f"/v1/workspaces/{ws_b}/memory/{m['id']}", headers=b.h)).status_code == 404


async def test_memory_api_lifecycle_and_privacy(client, signup, activate_plan, provider):
    owner, editor, ws = await _agency(client, signup, activate_plan)
    shared = (await client.post(f"/v1/workspaces/{ws}/memory", headers=editor.h,
                                json={"content": "Client hates exclamation marks", "kind": "brand_rule"})).json()
    private = (await client.post(f"/v1/workspaces/{ws}/memory", headers=editor.h,
                                 json={"content": "I draft best before noon", "visibility": "private"})).json()
    dup = await client.post(f"/v1/workspaces/{ws}/memory", headers=editor.h, json={"content": "client hates exclamation marks"})
    assert dup.status_code == 409
    owner_view = {m["id"] for m in (await client.get(f"/v1/workspaces/{ws}/memory", headers=owner.h)).json()["data"]}
    assert owner_view == {shared["id"]}  # the org owner can't see the editor's private memory
    assert (await client.delete(f"/v1/workspaces/{ws}/memory/{private['id']}", headers=owner.h)).status_code == 404
    r = await client.patch(f"/v1/workspaces/{ws}/memory/{shared['id']}", headers=owner.h, json={"status": "archived"})
    assert r.json()["status"] == "archived"
    assert (await client.get(f"/v1/workspaces/{ws}/memory", headers=owner.h)).json()["data"] == []


async def test_proposed_memory_needs_confirmation(client, signup, make_workspace, provider):
    a = await signup("Ada")
    ws = await make_workspace(a)
    conv = await conversation(client, a, ws)
    provider.on("router", route("creator.assistant"))  # no explicit "remember" request
    provider.on("creator.assistant", reply("Got it.", memory_candidates=[
        {"kind": "preference", "content": "Prefers carousel posts", "user_quote": "we mostly do carousel posts",
         "visibility": "workspace"}]))
    r = (await send(client, a, ws, conv, "Ideas for next week? we mostly do carousel posts")).json()
    assert r["run"]["memory_saved"][0]["status"] == "proposed"
    proposed = (await client.get(f"/v1/workspaces/{ws}/memory?status=proposed", headers=a.h)).json()["data"]
    r = await client.patch(f"/v1/workspaces/{ws}/memory/{proposed[0]['id']}", headers=a.h, json={"status": "active"})
    assert r.json()["status"] == "active" and r.json()["source"] == "user_confirmed"
