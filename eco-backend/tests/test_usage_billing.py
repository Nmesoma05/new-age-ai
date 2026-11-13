"""Paid plans are unlimited while active; only Free is counted. Usage records are always kept."""
from datetime import timedelta


async def _conv(client, acct, ws):
    return (await client.post(f"/v1/workspaces/{ws}/conversations", headers=acct.h, json={})).json()["id"]


async def _send(client, acct, ws, conv, text="Write a post"):
    return await client.post(f"/v1/workspaces/{ws}/conversations/{conv}/messages", headers=acct.h, json={"content": text})


async def test_free_plan_limit_and_counter(client, signup, make_workspace, owner_db):
    a = await signup("Ada")
    ws = await make_workspace(a)
    conv = await _conv(client, a, ws)
    u = (await client.get(f"/v1/orgs/{a.org_id}/usage", headers=a.h)).json()
    assert u == {"plan": "free", "ai_unlimited": False, "free_monthly_limit": 30, "free_used_this_month": 0,
                 "free_remaining": 30}
    owner_db.execute("INSERT INTO usage_counters VALUES (%s, date_trunc('month', now())::date, 29)", (a.org_id,))
    assert (await _send(client, a, ws, conv)).status_code == 201
    u = (await client.get(f"/v1/orgs/{a.org_id}/usage", headers=a.h)).json()
    assert u["free_used_this_month"] == 30 and u["free_remaining"] == 0
    r = await _send(client, a, ws, conv)
    assert r.status_code == 402 and r.json()["code"] == "free_limit_reached"
    # blocked generation stored nothing
    assert owner_db.execute("SELECT count(*) FROM messages").fetchone()[0] == 2


async def test_failed_generation_is_recorded_but_not_counted(client, signup, make_workspace, provider, owner_db):
    a = await signup("Ada")
    ws = await make_workspace(a)
    conv = await _conv(client, a, ws)
    provider.fail = "provider_http_500"
    r = await _send(client, a, ws, conv)
    assert r.status_code == 502 and r.json()["code"] == "ai_failed"
    assert owner_db.execute("SELECT status, counted_free FROM ai_usage_records").fetchall() == [("failed", False)]
    assert owner_db.execute("SELECT count(*) FROM messages").fetchone()[0] == 0
    assert (await client.get(f"/v1/orgs/{a.org_id}/usage", headers=a.h)).json()["free_used_this_month"] == 0


async def test_paid_plan_is_unlimited_and_shows_no_counter(client, signup, make_workspace, activate_plan, owner_db):
    a = await signup("Ada")
    await activate_plan(a.org_id, "pro")
    ws = await make_workspace(a)
    conv = await _conv(client, a, ws)
    owner_db.execute("INSERT INTO usage_counters VALUES (%s, date_trunc('month', now())::date, 30)", (a.org_id,))
    for _ in range(5):
        assert (await _send(client, a, ws, conv)).status_code == 201
    u = (await client.get(f"/v1/orgs/{a.org_id}/usage", headers=a.h)).json()
    assert u == {"plan": "pro", "ai_unlimited": True, "free_monthly_limit": None, "free_used_this_month": None,
                 "free_remaining": None}
    rows = owner_db.execute("SELECT counted_free, tokens_in, tokens_out, cost_usd FROM ai_usage_records "
                            "WHERE agent <> 'router'").fetchall()
    assert len(rows) == 5 and all(not r[0] for r in rows)
    assert owner_db.execute("SELECT count(*) FROM agent_runs WHERE status = 'succeeded'").fetchone()[0] == 5
    assert str(rows[0][3]) == "0.003000"  # 1000 in @ $1/M + 500 out @ $4/M (test prices)
    sub = (await client.get(f"/v1/orgs/{a.org_id}/subscription", headers=a.h)).json()
    assert sub["plan"] == "pro" and sub["ai_unlimited"] and sub["status"] == "active"


async def test_cancelled_keeps_access_until_period_end_then_free(client, signup, make_workspace, activate_plan, owner_db):
    a = await signup("Ada")
    await activate_plan(a.org_id, "pro", days=30)
    from app.core.db import transaction
    from app.services import subscriptions
    async with transaction(None, context="system") as s:
        await subscriptions.cancel(s, org_id=a.org_id)
    assert (await client.get(f"/v1/orgs/{a.org_id}/usage", headers=a.h)).json()["ai_unlimited"] is True
    # time passes: the paid period ends
    owner_db.execute("UPDATE subscriptions SET period_start = now() - interval '40 days', "
                     "period_end = now() - interval '1 day' WHERE org_id = %s", (a.org_id,))
    assert (await client.get(f"/v1/orgs/{a.org_id}/usage", headers=a.h)).json()["plan"] == "free"
    async with transaction(None, context="system") as s:
        assert await subscriptions.expire_due(s) == 1


async def test_prepaid_renewal_extends_from_current_end(client, signup, activate_plan, owner_db):
    a = await signup("Ada")
    await activate_plan(a.org_id, "pro", days=30)
    end1 = owner_db.execute("SELECT period_end FROM subscriptions WHERE org_id = %s", (a.org_id,)).fetchone()[0]
    await activate_plan(a.org_id, "pro", days=30)
    rows = owner_db.execute("SELECT period_end, status FROM subscriptions WHERE org_id = %s", (a.org_id,)).fetchall()
    assert len(rows) == 1 and abs((rows[0][0] - end1) - timedelta(days=30)) < timedelta(seconds=1)


async def test_downgrade_makes_extra_workspaces_read_only(client, signup, make_workspace, activate_plan, owner_db):
    a = await signup("Ada")
    await activate_plan(a.org_id, "pro")
    ws1, ws2 = await make_workspace(a, "First"), await make_workspace(a, "Second")
    owner_db.execute("UPDATE subscriptions SET period_start = now() - interval '40 days', "
                     "period_end = now() - interval '1 day' WHERE org_id = %s", (a.org_id,))
    post = {"type": "post", "title": "x", "body": {}}
    assert (await client.post(f"/v1/workspaces/{ws1}/assets", headers=a.h, json=post)).status_code == 201
    r = await client.post(f"/v1/workspaces/{ws2}/assets", headers=a.h, json=post)
    assert r.status_code == 403 and r.json()["code"] == "plan_limit_read_only"
    assert (await client.get(f"/v1/workspaces/{ws2}/assets", headers=a.h)).status_code == 200  # still readable
    listed = {w["name"]: w["read_only"] for w in (await client.get(f"/v1/orgs/{a.org_id}/workspaces", headers=a.h)).json()}
    assert listed == {"First": False, "Second": True}


async def test_workspace_limit_on_free(client, signup, make_workspace):
    a = await signup("Ada")
    await make_workspace(a, "One")
    r = await client.post(f"/v1/orgs/{a.org_id}/workspaces", headers=a.h, json={"name": "Two", "product": "creator"})
    assert r.status_code == 402 and r.json()["code"] == "workspace_limit_reached"


async def test_fair_use_threshold(client, signup, make_workspace, activate_plan, owner_db, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "fair_use_monthly_usd_per_user", 0.005)
    a = await signup("Ada")
    await activate_plan(a.org_id, "pro")
    ws = await make_workspace(a)
    conv = await _conv(client, a, ws)
    assert (await _send(client, a, ws, conv)).status_code == 201  # $0.003
    assert (await _send(client, a, ws, conv)).status_code == 201  # $0.006 total
    r = await _send(client, a, ws, conv)
    assert r.status_code == 429 and r.json()["code"] == "fair_use_review" and r.headers["retry-after"]


async def test_rate_limit_per_minute(client, signup, make_workspace, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "ai_rate_limit_per_minute", 2)
    a = await signup("Ada")
    ws = await make_workspace(a)
    conv = await _conv(client, a, ws)
    assert (await _send(client, a, ws, conv)).status_code == 201
    assert (await _send(client, a, ws, conv)).status_code == 201
    assert (await _send(client, a, ws, conv)).json()["code"] == "rate_limited"
