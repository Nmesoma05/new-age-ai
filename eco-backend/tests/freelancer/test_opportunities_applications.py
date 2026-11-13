"""Freelancer workflow 3: opportunities (eligibility, time zones, red flags, verification, expiry), application
tracker, and mock interviews."""
from datetime import date, timedelta


async def _opp(client, a, ws, **kw):
    body = {"title": "Product Designer", "organisation": "PayCo", "url": "https://payco.example/jobs/1",
            "source_name": "Remote board", "remote_type": "remote_regional", "eligible_countries": ["EMEA"],
            "timezone_requirement": {"tz": "America/New_York", "start_hour": 9, "end_hour": 17},
            "pay_min": "2000", "pay_max": "3000", "pay_currency": "USD", "pay_period": "month",
            "description": "Figma, fintech onboarding."}
    r = await client.post(f"/v1/workspaces/{ws}/freelancer/opportunities", headers=a.h, json={**body, **kw})
    assert r.status_code == 201, r.text
    return r.json()


async def test_opportunity_checks(client, fl):
    a, ws = await fl()
    o = await _opp(client, a, ws)
    c = o["checks"]
    assert o["status"] == "unverified" and o["source"] == "pasted"
    assert c["eligibility"]["status"] == "eligible" and "Confirm at the source" in c["eligibility"]["reasons"][0]
    assert c["timezone"]["overlap_hours"] in (5.0, 6.0)  # 5 in winter, 6 when New York is on daylight time
    assert c["risk_signals"] == [] and "listing's currency" in c["pay_note"]
    us = await _opp(client, a, ws, title="US only", eligible_countries=["US", "CA"])
    assert us["checks"]["eligibility"]["status"] == "not_eligible"
    scam = await _opp(client, a, ws, title="Data entry", remote_type="remote_global", eligible_countries=[],
                      description="No experience needed. Pay a small fee to start. Interview on Telegram only.")
    assert {s["signal"] for s in scam["checks"]["risk_signals"]} == {"upfront_fee", "chat_only"}
    unclear = await _opp(client, a, ws, title="Somewhere", remote_type="unknown", eligible_countries=[])
    assert unclear["checks"]["eligibility"]["status"] == "unclear"
    for bad in ({"eligible_countries": ["N1"]}, {"url": "ftp://x"}, {"pay_currency": None},
                {"timezone_requirement": {"tz": "Mars/Base", "start_hour": 9, "end_hour": 17}}):
        r = await client.post(f"/v1/workspaces/{ws}/freelancer/opportunities", headers=a.h,
                              json={"title": "x", "pay_min": "1", "pay_currency": "USD", **bad})
        assert r.status_code == 422, bad


async def test_verify_expire_and_analysis(client, fl, fgen, provider):
    a, ws = await fl()
    o = await _opp(client, a, ws)
    r = await client.post(f"/v1/workspaces/{ws}/freelancer/opportunities/{o['id']}/verify", headers=a.h,
                          json={"still_open": True, "note": "Checked on the company careers page"})
    assert r.json()["status"] == "verified" and r.json()["checks"]["verified"] is True
    old = await _opp(client, a, ws, title="Old", deadline=(date.today() - timedelta(days=2)).isoformat())
    listed = {x["id"]: x for x in (await client.get(f"/v1/workspaces/{ws}/freelancer/opportunities", headers=a.h)).json()}
    assert listed[old["id"]]["status"] == "expired"
    r = await client.post(f"/v1/workspaces/{ws}/freelancer/opportunities/{old['id']}/verify", headers=a.h,
                          json={"still_open": True})
    assert r.status_code == 409 and r.json()["code"] == "deadline_passed"
    closed = await _opp(client, a, ws, title="Gone")
    r = await client.post(f"/v1/workspaces/{ws}/freelancer/opportunities/{closed['id']}/verify", headers=a.h,
                          json={"still_open": False})
    assert r.json()["status"] == "closed"
    # Not eligible -> the analysis can't say a plain "apply"
    us = await _opp(client, a, ws, title="US only", eligible_countries=["US"])
    run = (await fgen(a, ws, tool="opportunity", opportunity_id=us["id"])).json()["run"]
    assert run["output"]["recommendation"] == "skip_or_clarify"
    task = next(m.content for m in provider.sent_to("freelancer.opportunity_analyst")[-1].messages if m.role == "user")
    assert "Eligibility (computed): not_eligible" in task and "NOT yet verified" in task
    assert "untrusted_data source=\"external:listing\"" in task


async def test_application_tracker(client, fl, fgen):
    a, ws = await fl()
    o = await _opp(client, a, ws)
    app_ = (await client.post(f"/v1/workspaces/{ws}/freelancer/opportunities/{o['id']}/track", headers=a.h)).json()
    assert app_["status"] == "preparing" and app_["opportunity_id"] == o["id"] and app_["history"][0]["note"] == "Created"
    cv_run = (await fgen(a, ws, tool="cv", target_role="Product designer")).json()["run"]
    cv = (await client.post(f"/v1/workspaces/{ws}/freelancer/runs/{cv_run['id']}/save", headers=a.h, json={})).json()
    base = f"/v1/workspaces/{ws}/freelancer/applications/{app_['id']}"
    assert (await client.patch(base, headers=a.h, json={"letter_asset_id": cv["id"]})).status_code == 422
    due = (date.today() - timedelta(days=1)).isoformat()
    r = await client.patch(base, headers=a.h, json={"status": "applied", "status_note": "Applied on their site",
                                                     "cv_asset_id": cv["id"], "next_step": "Follow up by email",
                                                     "next_step_due": due})
    j = r.json()
    assert j["status"] == "applied" and j["applied_on"] == date.today().isoformat() and j["cv_asset_id"] == cv["id"]
    assert [h["status"] for h in j["history"]] == ["preparing", "applied"]
    ov = (await client.get(f"/v1/workspaces/{ws}/freelancer/overview", headers=a.h)).json()
    assert ov["counts"]["follow_ups_due"] == 1 and ov["follow_ups"][0]["overdue"] is True
    assert ov["next_steps"][0]["tool"] in ("applications", "assessment")
    r = await client.patch(base, headers=a.h, json={"status": "interviewing"})
    assert len(r.json()["history"]) == 3
    lst = (await client.get(f"/v1/workspaces/{ws}/freelancer/applications?status=interviewing", headers=a.h)).json()
    assert len(lst) == 1
    manual = await client.post(f"/v1/workspaces/{ws}/freelancer/applications", headers=a.h,
                               json={"title": "Logo job", "organisation": "Bakery", "status": "applied"})
    assert manual.status_code == 201
    assert (await client.delete(f"/v1/workspaces/{ws}/freelancer/applications/{manual.json()['id']}", headers=a.h)).status_code == 204


async def test_mock_interview(client, fl, fgen, provider):
    a, ws = await fl()
    prep = (await fgen(a, ws, tool="interview", target_role="Product designer", question_count=4)).json()["run"]
    r = await client.post(f"/v1/workspaces/{ws}/freelancer/interviews", headers=a.h,
                          json={"role_title": "Product designer", "run_id": prep["id"],
                                "questions": ["Why remote work?"]})
    s = r.json()
    assert r.status_code == 201 and len(s["questions"]) == 5 and s["questions"][-1]["type"] == "own"
    base = f"/v1/workspaces/{ws}/freelancer/interviews/{s['id']}"
    r = await client.post(f"{base}/answers", headers=a.h, json={"index": 0, "answer":
                          "At Kola Studio I simplified a savings app's onboarding because people dropped off."})
    assert r.status_code == 201, r.text
    fb = r.json()
    assert fb["feedback"]["scores"]["specificity"] == 2 and "A stronger version" in fb["feedback_text"]
    task = next(m.content for m in provider.sent_to("freelancer.answer_coach")[-1].messages if m.role == "user")
    assert "My answer: At Kola Studio" in task
    assert (await client.post(f"{base}/answers", headers=a.h, json={"index": 9, "answer": "x" * 30})).status_code == 422
    assert (await client.post(f"{base}/answers", headers=a.h, json={"index": 1, "answer": "short"})).status_code == 422
    got = (await client.get(base, headers=a.h)).json()
    assert len(got["answers"]) == 1
    assert (await client.post(f"{base}/complete", headers=a.h)).json()["status"] == "completed"
    r = await client.post(f"{base}/answers", headers=a.h, json={"index": 1, "answer": "x" * 30})
    assert r.status_code == 409
    no_src = await client.post(f"/v1/workspaces/{ws}/freelancer/interviews", headers=a.h, json={"role_title": "X"})
    assert no_src.status_code == 422
