"""Freelancer workflow 1: onboarding, reusable profile, reference data, assessment, dashboard, privacy."""
from tests.freelancer.helpers import PROFILE


async def test_onboarding_creates_private_workspace(client, signup, owner_db):
    a = await signup("Chiamaka", product=None)
    st = (await client.get("/v1/freelancer/onboarding", headers=a.h)).json()
    assert st["next_step"] == "create_profile" and st["can_create"] is True
    r = await client.post("/v1/freelancer/onboarding", headers=a.h, json={"profile": PROFILE})
    assert r.status_code == 201, r.text
    ws = r.json()["workspace_id"]
    assert (await client.get("/v1/freelancer/onboarding", headers=a.h)).json()["workspace_id"] == ws
    again = await client.post("/v1/freelancer/onboarding", headers=a.h, json={"profile": PROFILE})
    assert again.status_code == 409 and again.json()["code"] == "already_set_up"
    kind = owner_db.execute("SELECT o.kind FROM workspaces w JOIN organisations o ON o.id=w.org_id WHERE w.id=%s",
                            (ws,)).fetchone()[0]
    assert kind == "personal"
    prof = (await client.get(f"/v1/workspaces/{ws}/professional-profile", headers=a.h)).json()
    assert prof["country"] == "NG" and prof["timezone"] == "Africa/Lagos" and prof["career_stage"] == "beginner"
    assert prof["skills"][2] == {"name": "Webflow"}  # empty fields aren't stored, so the AI only sees what was given
    assert prof["experiences"][0]["organisation"] == "Kola Studio"


async def test_profile_validation(client, signup):
    a = await signup("Chiamaka", product=None)
    for bad in ({"timezone": "Lagos"}, {"country": "Nigeria"}, {"currency": "naira"},
                {"links": [{"label": "x", "url": "javascript:alert(1)"}]}, {"career_stage": "ceo"},
                {"skills": [{"name": "Figma", "level": "god"}]}, {"rates": {"hourly": -5}}, {"surprise": 1}):
        r = await client.post("/v1/freelancer/onboarding", headers=a.h, json={"profile": {**PROFILE, **bad}})
        assert r.status_code == 422, bad
    # older clients' shape still accepted
    r = await client.post("/v1/freelancer/onboarding", headers=a.h, json={"profile": {
        "headline": "Designer", "experiences": [{"role": "Designer", "company": "Kola", "years": "2022"}]}})
    assert r.status_code == 201


async def test_reference_capabilities_rate_floor(client):
    ref = (await client.get("/v1/freelancer/reference")).json()
    ng = next(c for c in ref["countries"] if c["code"] == "NG")
    assert ng["currency"] == "NGN" and ng["timezone"] == "Africa/Lagos" and len(ref["countries"]) > 80
    assert ref["resources"]["checked_on"] == "2026-11-12" and all(r["source_url"].startswith("https://")
                                                                  for r in ref["resources"]["items"])
    assert {c["key"] for c in ref["conventions"]} >= {"us", "uk", "global_remote", "africa_local"}
    caps = {f["feature"]: f["status"] for f in (await client.get("/v1/freelancer/capabilities")).json()["features"]}
    assert caps["Live job feeds / auto-apply"] == "requires_integration" and caps["Remote job discovery"] == "manual"
    f = (await client.post("/v1/freelancer/rate-floor", json={"income_goal_monthly": 600, "hours_per_week": 30})).json()
    assert f["hourly_floor"] == 7.69 and f["billable_hours_per_month"] == 78.0
    assert (await client.post("/v1/freelancer/rate-floor", json={"income_goal_monthly": 0, "hours_per_week": 30})).status_code == 422


async def test_assessment_generate_apply_edit(client, fl, fgen, provider):
    a, ws = await fl()
    r = await fgen(a, ws, tool="assessment")
    assert r.status_code == 201, r.text
    run = r.json()["run"]
    assert run["agent"] == "freelancer.skills_assessor" and run["status"] == "succeeded"
    sent = provider.sent_to("freelancer.skills_assessor")[0].messages[-1].content
    assert "Career stage: Skilled, no clients yet" in sent and "Cross-border notes" in sent and "Payoneer" in sent
    prof = (await client.get(f"/v1/workspaces/{ws}/professional-profile", headers=a.h)).json()
    assert prof["assessment"] == {}  # not applied until the user chooses
    r = await client.post(f"/v1/workspaces/{ws}/freelancer/runs/{run['id']}/apply-assessment", headers=a.h)
    assert r.status_code == 200 and r.json()["assessment"]["skills"][0]["evidence_level"] == "shown"
    edit = {k: r.json()["assessment"][k] for k in ("summary", "stage_read", "skills", "strengths", "gaps",
                                                   "suggested_directions", "headline_options")}
    edit["strengths"] = ["Calm, clear onboarding design"]
    r = await client.put(f"/v1/workspaces/{ws}/freelancer/assessment", headers=a.h, json=edit)
    assert r.status_code == 200 and r.json()["assessment"]["edited_by_user"] is True
    assert r.json()["assessment"]["source_run_id"] == run["id"]
    bad = {**edit, "skills": [{"skill": "X", "evidence_level": "guru"}]}
    assert (await client.put(f"/v1/workspaces/{ws}/freelancer/assessment", headers=a.h, json=bad)).status_code == 422
    # the AI assessment is never offered back to the model as evidence
    await fgen(a, ws, tool="cv")
    tool_text = next(m.content for m in provider.sent_to("freelancer.cv_writer")[-1].messages if m.role == "tool")
    assert "Calm, clear onboarding design" not in tool_text


async def test_dashboard_by_stage(client, fl):
    a, ws = await fl()
    ov = (await client.get(f"/v1/workspaces/{ws}/freelancer/overview", headers=a.h)).json()
    tools = [s["tool"] for s in ov["next_steps"]]
    assert tools[0] == "assessment" and "services" in tools and "cv" not in tools
    assert ov["profile"]["completeness"] >= 80 and ov["profile"]["country_name"] == "Nigeria"
    b, ws2 = await fl("Bola", career_stage="job_seeker")
    tools2 = [s["tool"] for s in (await client.get(f"/v1/workspaces/{ws2}/freelancer/overview", headers=b.h)).json()["next_steps"]]
    assert "cv" in tools2 and "opportunities" in tools2 and "services" not in tools2


async def test_privacy_and_product(client, signup, make_workspace, fl, fgen, provider):
    a, ws = await fl()
    b, ws_b = await fl("Bola", summary="SECRET-B-SUMMARY")
    assert (await client.get(f"/v1/workspaces/{ws}/freelancer/overview", headers=b.h)).status_code == 404
    c = await signup("Cee")
    cws = await make_workspace(c)
    r = await client.get(f"/v1/workspaces/{cws}/freelancer/overview", headers=c.h)
    assert r.status_code == 409 and r.json()["code"] == "wrong_product"
    await fgen(a, ws, tool="assessment")
    from tests.ai.scripted import everything_sent
    assert all("SECRET-B-SUMMARY" not in everything_sent(q) for q in provider.requests)
