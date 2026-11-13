"""Business workflow 1: onboarding, businesses list, Intelligence Profile (generate, apply, edit), dashboard."""
from tests.business.helpers import BIZ


async def test_onboarding_and_list(client, signup, biz_onboard, owner_db):
    a = await signup("Ada", product=None)
    st = (await client.get("/v1/business/onboarding", headers=a.h)).json()
    assert st["next_step"] == "create_first_business" and st["businesses"] == []
    res = await biz_onboard(a)
    assert res["org_id"] == str(a.org_id)
    rows = (await client.get("/v1/business/businesses", headers=a.h)).json()
    assert rows[0]["business_name"] == BIZ["business_name"] and rows[0]["category"] == "food_hospitality"
    assert rows[0]["profile_complete"] == 100 and rows[0]["has_intelligence"] is False
    prof = (await client.get(f"/v1/workspaces/{res['workspace_id']}/business-profile", headers=a.h)).json()
    assert prof["budget"] == {"monthly_amount": 50000.0, "currency": "NGN", "notes": "Can increase in December"}
    assert prof["competitors"][0]["name"] == "Chop Express" and prof["channels"][0]["channel"] == "whatsapp"
    acts = [r[0] for r in owner_db.execute("SELECT action FROM audit_events").fetchall()]
    assert "org.product_enrolled" in acts and "profile.business_saved" in acts


async def test_validation_and_categories(client, signup):
    a = await signup("Ada", product=None)
    for bad in ({"category": "spaceships"}, {"stage": "unicorn"}, {"budget": {"monthly_amount": -5, "currency": "NGN"}},
                {"budget": {"monthly_amount": 5, "currency": "naira"}}, {"channels": [{"channel": "myspace"}]},
                {"website": "javascript:alert(1)"}):
        r = await client.post("/v1/business/onboarding", headers=a.h, json={"mode": "solo", "profile": {**BIZ, **bad}})
        assert r.status_code == 422, bad
    assert (await client.post("/v1/business/onboarding", headers=a.h,
                              json={"mode": "team", "profile": BIZ})).status_code == 422
    cats = (await client.get("/v1/business/categories")).json()
    assert len(cats["categories"]) == 16 and {s["key"] for s in cats["stages"]} == {"idea", "new", "growing", "established"}
    assert len(cats["channels"]) == 21


async def test_capabilities_are_honest(client):
    status = {f["feature"]: f["status"] for f in (await client.get("/v1/business/capabilities")).json()["features"]}
    assert status["Launching ads / spending budget"] == "requires_integration"
    assert status["Automatic results import (ads, CRM, analytics, sales)"] == "requires_integration"
    assert status["Competitor analysis"] == "manual" and status["Marketing plan generator"] == "operational"


async def test_intelligence_generate_apply_edit(client, biz, bgen, provider):
    a, ws = await biz()
    r = await bgen(a, ws, tool="intelligence")
    assert r.status_code == 201, r.text
    run = r.json()["run"]
    assert run["agent"] == "business.profile_builder" and run["status"] == "succeeded"
    sent = provider.sent_to("business.profile_builder")[0].messages[-1].content
    assert "Category: Food & hospitality" in sent or "food" in sent.lower()
    assert "Budget: 50,000 NGN per month" in sent and "At this stage:" in sent
    # Not applied until the owner says so
    prof = (await client.get(f"/v1/workspaces/{ws}/business-profile", headers=a.h)).json()
    assert prof["intelligence"] == {}
    r = await client.post(f"/v1/workspaces/{ws}/business/runs/{run['id']}/apply-intelligence", headers=a.h)
    assert r.status_code == 200 and r.json()["intelligence"]["channel_fit"][0]["channel"] == "whatsapp"
    edit = {**{k: v for k, v in r.json()["intelligence"].items() if k not in ("source_run_id", "uncertainties")},
            "priorities": ["Get 10 Google reviews"], "channel_fit": []}
    r = await client.put(f"/v1/workspaces/{ws}/business/intelligence", headers=a.h, json=edit)
    assert r.status_code == 200, r.text
    assert r.json()["intelligence"]["priorities"] == ["Get 10 Google reviews"] and r.json()["intelligence"]["edited_by_user"]
    bad = {**edit, "channel_fit": [{"channel": "myspace", "fit": "strong"}]}
    assert (await client.put(f"/v1/workspaces/{ws}/business/intelligence", headers=a.h, json=bad)).status_code == 422
    # The edited profile is what later tools see
    await bgen(a, ws, tool="positioning")
    from tests.ai.scripted import call
    provider.on("business.marketing_planner", call("get_profile", {}))
    await bgen(a, ws, tool="plan")
    seen = provider.sent_to("business.marketing_planner")[1].messages[-1].content
    assert "Get 10 Google reviews" in seen


async def test_dashboard_adapts(client, biz, bgen):
    a, ws = await biz(stage="idea", business_model="b2b", category="b2b_tech", competitors=[])
    ov = (await client.get(f"/v1/workspaces/{ws}/business/overview", headers=a.h)).json()
    tools = [s["tool"] for s in ov["next_steps"]]
    assert tools[0] == "intelligence" and "market" in tools and "acquisition" in tools and "content" not in tools
    assert ov["business"]["stage_label"] == "Idea / pre-launch" and ov["pending_approvals"] == 0
    assert ov["results_30d"]["rows"] == 0 and ov["integrations"]["ads"] == "requires_integration"
    a2, ws2 = await biz("Bea")
    tools2 = [s["tool"] for s in (await client.get(f"/v1/workspaces/{ws2}/business/overview", headers=a2.h)).json()["next_steps"]]
    assert "content" in tools2 and "acquisition" not in tools2


async def test_wrong_product_and_isolation(client, signup, make_workspace, biz, bgen, provider):
    a, ws = await biz()
    c = await signup("Cee")  # creator
    cws = await make_workspace(c)
    r = await client.get(f"/v1/workspaces/{cws}/business/overview", headers=c.h)
    assert r.status_code == 409 and r.json()["code"] == "wrong_product"
    assert (await client.get(f"/v1/workspaces/{ws}/business/overview", headers=c.h)).status_code == 404
    b, ws_b = await biz("Bea", business_name="Secret Spa", differentiators="SECRET-DIFF-B")
    await bgen(a, ws, tool="intelligence")
    from tests.ai.scripted import everything_sent
    assert all("SECRET-DIFF-B" not in everything_sent(q) for q in provider.sent_to("business.profile_builder"))
