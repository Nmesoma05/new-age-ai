"""Business workflow 2: every strategy tool, saving to projects, editing, exporting, campaigns, approvals."""
from tests.ai.scripted import final


async def test_every_tool_runs_and_holds_to_the_request(client, biz, bgen, provider):
    a, ws = await biz()
    cases = [({"tool": "positioning"}, "business.positioning_strategist", None),
             ({"tool": "market"}, "business.market_analyst", "Focus: market"),
             ({"tool": "competitors"}, "business.market_analyst", "Competitors to compare: Chop Express"),
             ({"tool": "plan", "plan_months": 6}, "business.marketing_planner", "Plan length: 6 months"),
             ({"tool": "content", "platforms": ["instagram", "whatsapp"]}, "business.aida_strategist",
              "Platforms: instagram, whatsapp"),
             ({"tool": "ads", "start_date": "2026-12-01", "end_date": "2026-12-24"}, "business.ads_planner",
              "Date range: 2026-12-01 to 2026-12-24"),
             ({"tool": "acquisition"}, "business.growth_strategist", "Focus: acquisition"),
             ({"tool": "retention"}, "business.growth_strategist", "Focus: retention")]
    for body, agent, line in cases:
        r = await bgen(a, ws, **body)
        assert r.status_code == 201, (body, r.text)
        run = r.json()["run"]
        assert run["agent"] == agent and run["status"] == "succeeded", (body, run)
        if line:
            assert line in provider.sent_to(agent)[-1].messages[-1].content
    out = (await bgen(a, ws, tool="plan", plan_months=6)).json()["run"]["output"]
    assert out["plan_months"] == 6 and len(out["timeline"]) == 6
    # Each run gets its own conversation
    convs = (await client.get(f"/v1/workspaces/{ws}/conversations", headers=a.h)).json()
    titles = [c["title"] for c in convs["data"]]
    assert len([t for t in titles if t.startswith("Studio · ")]) == 9


async def test_competitors_need_names_and_report_needs_results(client, biz, bgen):
    a, ws = await biz(competitors=[])
    r = await bgen(a, ws, tool="competitors")
    assert r.status_code == 422 and r.json()["code"] == "no_competitors"
    r = await bgen(a, ws, tool="report", start_date="2026-11-01", end_date="2026-11-30")
    assert r.status_code == 422 and r.json()["code"] == "no_results"
    assert (await bgen(a, ws, tool="ads")).status_code == 422  # needs dates


async def test_save_to_project_edit_export(client, biz, bgen):
    a, ws = await biz()
    proj = (await client.post(f"/v1/workspaces/{ws}/projects", headers=a.h, json={"name": "December push"})).json()
    run = (await bgen(a, ws, tool="plan")).json()["run"]
    r = await client.post(f"/v1/workspaces/{ws}/business/runs/{run['id']}/save", headers=a.h,
                          json={"project_id": proj["id"], "title": "Q4 plan"})
    assert r.status_code == 201, r.text
    asset = r.json()
    assert asset["type"] == "marketing_plan" and asset["project_id"] == proj["id"] and asset["status"] == "draft"
    work = (await client.get(f"/v1/workspaces/{ws}/business/work?project_id={proj['id']}", headers=a.h)).json()
    assert [w["id"] for w in work] == [asset["id"]]
    # Edit = new version (shared versioning API)
    r = await client.post(f"/v1/workspaces/{ws}/assets/{asset['id']}/versions", headers=a.h,
                          json={"body": {"edited": True}, "body_text": "My edited plan <script>x</script>"})
    assert r.status_code == 201
    md = await client.get(f"/v1/workspaces/{ws}/business/work/{asset['id']}/export?format=md", headers=a.h)
    assert md.status_code == 200 and "My edited plan" in md.text and "attachment" in md.headers["content-disposition"]
    html = await client.get(f"/v1/workspaces/{ws}/business/work/{asset['id']}/export?format=html", headers=a.h)
    assert "<script>" not in html.text and "&lt;script&gt;" in html.text
    # Unfile it
    r = await client.patch(f"/v1/workspaces/{ws}/business/work/{asset['id']}/project", headers=a.h)
    assert r.json()["project_id"] is None
    other = (await client.post(f"/v1/workspaces/{ws}/business/runs/{run['id']}/save", headers=a.h, json={})).json()
    assert other["title"].startswith("Marketing plan · ")
    # A different tool's run can't be applied as something else
    r = await client.post(f"/v1/workspaces/{ws}/business/runs/{run['id']}/apply-intelligence", headers=a.h)
    assert r.status_code == 409


async def test_apply_positioning_parts(client, biz, bgen):
    a, ws = await biz()
    run = (await bgen(a, ws, tool="positioning")).json()["run"]
    r = await client.post(f"/v1/workspaces/{ws}/business/runs/{run['id']}/apply-positioning", headers=a.h,
                          json={"parts": ["positioning", "messages"]})
    assert r.status_code == 200
    brand = (await client.get(f"/v1/workspaces/{ws}/business-profile", headers=a.h)).json()["brand"]
    assert brand["taglines"] == ["Done right, on time.", "Care you can count on."] and "tone_guidance" not in brand


async def test_ads_to_campaign_and_approval_never_spends(client, biz, bgen, activate_plan, owner_db, signup):
    a, ws = await biz()
    run = (await bgen(a, ws, tool="ads", start_date="2026-12-01", end_date="2026-12-24")).json()["run"]
    c = (await client.post(f"/v1/workspaces/{ws}/business/runs/{run['id']}/create-campaign", headers=a.h)).json()
    assert c["status"] == "draft" and c["channels"] == ["meta_ads"] and c["start_date"] == "2026-12-01"
    # Spending needs an amount
    r = await client.post(f"/v1/workspaces/{ws}/business/approvals", headers=a.h,
                          json={"kind": "spend_money", "run_id": run["id"], "title": "Launch December ads"})
    assert r.status_code == 422
    r = await client.post(f"/v1/workspaces/{ws}/business/approvals", headers=a.h,
                          json={"kind": "spend_money", "run_id": run["id"], "title": "Launch December ads",
                                "amount": "30000", "currency": "NGN", "channel": "meta_ads"})
    assert r.status_code == 201, r.text
    pa = r.json()
    assert pa["status"] == "awaiting_approval" and pa["kind"] == "spend_money"
    r = await client.post(f"/v1/workspaces/{ws}/actions/{pa['id']}/approve", headers=a.h, json={})
    assert r.status_code == 409 and r.json()["code"] == "no_executor"
    assert owner_db.execute("SELECT status FROM pending_actions WHERE id=%s", (pa["id"],)).fetchone()[0] == "awaiting_approval"
    r = await client.post(f"/v1/workspaces/{ws}/actions/{pa['id']}/reject", headers=a.h, json={"reason": "Later"})
    assert r.json()["status"] == "rejected"
    # Messages need a messaging channel
    r = await client.post(f"/v1/workspaces/{ws}/business/approvals", headers=a.h,
                          json={"kind": "send_message", "run_id": run["id"], "title": "Broadcast", "channel": "instagram"})
    assert r.status_code == 422


async def test_viewer_cannot_write(client, signup, biz_onboard, activate_plan, bgen):
    owner, viewer = await signup("Owner", product=None), await signup("Vee", product=None)
    res = await biz_onboard(owner, mode="team", team_name="Kitchen Team")
    await activate_plan(res["org_id"], "team")
    ws = res["workspace_id"]
    await client.post(f"/v1/orgs/{res['org_id']}/members", headers=owner.h, json={"email": viewer.email, "role": "member"})
    await client.post(f"/v1/workspaces/{ws}/members", headers=owner.h, json={"user_id": str(viewer.user_id), "role": "viewer"})
    assert (await client.get(f"/v1/workspaces/{ws}/business/overview", headers=viewer.h)).status_code == 200
    assert (await bgen(viewer, ws, tool="plan")).status_code == 403
    r = await client.post(f"/v1/workspaces/{ws}/business/results", headers=viewer.h,
                          json={"channel": "whatsapp", "period_start": "2026-11-01", "period_end": "2026-11-07", "leads": 3})
    assert r.status_code == 403


async def test_failed_tool_run_is_recorded(client, biz, bgen, provider):
    """Regression: a one-shot tool run that fails used to lose its record (its new conversation rolled back)."""
    a, ws = await biz()
    bad = final({"focus": "market", "sources_used": "Live web research", "market_insights": [], "customer_insights": [],
                 "competitors": [], "questions_to_validate": [], "recommendations": [], "uncertainties": [],
                 "warnings": [], "memory_candidates": []})
    provider.on("business.market_analyst", bad, bad)
    r = await bgen(a, ws, tool="market")
    assert r.status_code == 422
    runs = (await client.get(f"/v1/workspaces/{ws}/runs", headers=a.h)).json()["data"]
    assert runs[0]["status"] == "failed" and runs[0]["agent"] == "business.market_analyst"
