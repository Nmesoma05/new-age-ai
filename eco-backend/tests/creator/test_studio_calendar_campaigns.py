"""Workflows 2-4: content studio (generate → save → edit), brand voice, calendar planning and campaigns."""


async def test_content_generate_save_edit(client, creator, gen, provider, owner_db):
    a, ws = await creator()
    r = await gen(a, ws, kind="content", brief="Weekday morning cold brew push", platforms=["instagram", "x"], count=3)
    assert r.status_code == 201, r.text
    run = r.json()["run"]
    assert run["agent"] == "creator.content_writer" and len(run["output"]["drafts"]) == 3
    sent = provider.sent_to("creator.content_writer")[0].messages[-1].content
    assert "Platforms: instagram, x" in sent and "Number of drafts: 3" in sent
    conv_title = owner_db.execute("SELECT title FROM conversations").fetchone()[0]
    assert conv_title.startswith("Studio · content:")
    saved = await client.post(f"/v1/workspaces/{ws}/creator/runs/{run['id']}/save-drafts", headers=a.h,
                              json={"indexes": [0, 2]})
    assert saved.status_code == 201 and len(saved.json()) == 2
    asset = saved.json()[0]
    assert asset["status"] == "draft" and asset["tags"] == ["instagram"]
    v = (await client.get(f"/v1/workspaces/{ws}/assets/{asset['id']}/versions", headers=a.h)).json()
    assert v[0]["source"] == "ai" and v[0]["body"]["platform"] == "instagram" and "Hook:" in v[0]["body_text"]
    edit = await client.post(f"/v1/workspaces/{ws}/assets/{asset['id']}/versions", headers=a.h,
                             json={"body": {**v[0]["body"], "body": "Edited by hand"}, "body_text": "Edited by hand"})
    assert edit.status_code == 201 and edit.json()["version"] == 2 and edit.json()["source"] == "human"
    bad = await client.post(f"/v1/workspaces/{ws}/creator/runs/{run['id']}/save-drafts", headers=a.h,
                            json={"indexes": [7]})
    assert bad.status_code == 422


async def test_wrong_run_type_refused(client, creator, gen):
    a, ws = await creator()
    run = (await gen(a, ws, kind="brand_voice", brief="Refresh our voice")).json()["run"]
    r = await client.post(f"/v1/workspaces/{ws}/creator/runs/{run['id']}/save-drafts", headers=a.h, json={})
    assert r.status_code == 409 and r.json()["code"] == "wrong_run"


async def test_brand_voice_apply_only_chosen_parts(client, creator, gen):
    a, ws = await creator()
    run = (await gen(a, ws, kind="brand_voice", brief="Define our voice")).json()["run"]
    before = (await client.get(f"/v1/workspaces/{ws}/client-account", headers=a.h)).json()
    r = await client.post(f"/v1/workspaces/{ws}/creator/runs/{run['id']}/apply-brand", headers=a.h,
                          json={"parts": ["voice", "pillars"]})
    assert r.status_code == 200 and r.json()["version"] == before["version"] + 1
    after = (await client.get(f"/v1/workspaces/{ws}/client-account", headers=a.h)).json()
    assert after["brand_voice"]["tone"] == "warm, witty"  # existing keys kept
    assert after["brand_voice"]["words_to_avoid"] == ["cheap"]
    assert [p["name"] for p in after["content_pillars"]] == ["Craft", "Community"]
    assert after["audience"] == before["audience"]  # personas not chosen, so untouched


async def test_calendar_plan_import_edit_export(client, creator, gen):
    a, ws = await creator()
    r = await gen(a, ws, kind="calendar", brief="December plan", start_date="2026-12-01", end_date="2026-12-14",
                  platforms=["instagram", "x"])
    assert r.status_code == 201, r.text
    run = r.json()["run"]
    imp = await client.post(f"/v1/workspaces/{ws}/creator/runs/{run['id']}/import-calendar", headers=a.h, json={})
    assert imp.status_code == 201
    items = imp.json()
    assert len(items) == 7 and {i["source"] for i in items} == {"ai_plan"}
    assert items[0]["scheduled_for"].startswith("2026-12-01T08:00:00")  # 09:00 Africa/Lagos = 08:00 UTC
    listed = (await client.get(f"/v1/workspaces/{ws}/creator/calendar?start=2026-12-01&end=2026-12-31",
                               headers=a.h)).json()
    assert len(listed) == 7
    p = await client.patch(f"/v1/workspaces/{ws}/creator/calendar/{items[0]['id']}", headers=a.h,
                           json={"status": "ready", "title": "Roast day reel"})
    assert p.json()["status"] == "ready"
    bad = await client.patch(f"/v1/workspaces/{ws}/creator/calendar/{items[0]['id']}", headers=a.h,
                             json={"status": "published_manually"})
    assert bad.status_code == 422  # only mark-published can set that
    csv_ = await client.get(f"/v1/workspaces/{ws}/creator/calendar/export?format=csv&start=2026-12-01&end=2026-12-31",
                            headers=a.h)
    assert csv_.headers["content-type"].startswith("text/csv") and "Roast day reel" in csv_.text
    ics = await client.get(f"/v1/workspaces/{ws}/creator/calendar/export?format=ics&start=2026-12-01&end=2026-12-31",
                           headers=a.h)
    assert ics.text.startswith("BEGIN:VCALENDAR") and ics.text.count("BEGIN:VEVENT") == 7
    assert "DTSTART:20261201T080000Z" in ics.text


async def test_calendar_request_validation(client, creator, gen):
    a, ws = await creator()
    r = await gen(a, ws, kind="calendar", brief="Too long", start_date="2026-12-01", end_date="2027-06-01")
    assert r.status_code == 422
    r = await gen(a, ws, kind="calendar", brief="No dates")
    assert r.status_code == 422


async def test_manual_calendar_item_and_manual_publish_rules(client, creator):
    a, ws = await creator()
    asset = (await client.post(f"/v1/workspaces/{ws}/assets", headers=a.h,
                               json={"type": "post", "title": "Cold brew is back", "body": {}, "body_text": "x"})).json()
    item = (await client.post(f"/v1/workspaces/{ws}/creator/calendar", headers=a.h, json={
        "title": "Cold brew is back", "platform": "instagram", "scheduled_for": "2026-12-05T09:00:00+01:00",
        "asset_id": asset["id"]})).json()
    assert item["status"] == "drafted" and item["asset_title"] == "Cold brew is back"
    r = await client.post(f"/v1/workspaces/{ws}/creator/calendar/{item['id']}/mark-published", headers=a.h, json={})
    assert r.status_code == 409 and r.json()["code"] == "not_approved"
    await client.patch(f"/v1/workspaces/{ws}/assets/{asset['id']}", headers=a.h, json={"status": "approved"})
    r = await client.post(f"/v1/workspaces/{ws}/creator/calendar/{item['id']}/mark-published", headers=a.h,
                          json={"published_url": "https://instagram.com/p/abc"})
    assert r.json()["status"] == "published_manually" and r.json()["asset_status"] == "posted"
    r = await client.patch(f"/v1/workspaces/{ws}/creator/calendar/{item['id']}", headers=a.h, json={"status": "ready"})
    assert r.json()["published_at"] is None and r.json()["published_url"] is None
    bad = await client.post(f"/v1/workspaces/{ws}/creator/calendar/{item['id']}/mark-published", headers=a.h,
                            json={"published_url": "javascript:alert(1)"})
    assert bad.status_code == 422


async def test_campaign_from_plan_and_crud(client, creator, gen):
    a, ws = await creator()
    run = (await gen(a, ws, kind="campaign", brief="Cold brew launch", start_date="2027-01-05",
                     end_date="2027-02-05", platforms=["instagram"])).json()["run"]
    c = await client.post(f"/v1/workspaces/{ws}/creator/runs/{run['id']}/create-campaign", headers=a.h)
    assert c.status_code == 201
    camp = c.json()
    assert camp["start_date"] == "2027-01-05" and camp["plan"]["phases"][0]["name"] == "Tease"
    cal = (await gen(a, ws, kind="calendar", brief="Launch posts", start_date="2027-01-05", end_date="2027-01-10")).json()
    await client.post(f"/v1/workspaces/{ws}/creator/runs/{cal['run']['id']}/import-calendar", headers=a.h,
                      json={"campaign_id": camp["id"], "indexes": [0, 1]})
    detail = (await client.get(f"/v1/workspaces/{ws}/creator/campaigns/{camp['id']}", headers=a.h)).json()
    assert len(detail["calendar"]) == 2 and detail["counts"]["planned"] == 2
    r = await client.patch(f"/v1/workspaces/{ws}/creator/campaigns/{camp['id']}", headers=a.h,
                           json={"status": "active", "end_date": "2026-01-01"})
    assert r.status_code == 422
    manual = await client.post(f"/v1/workspaces/{ws}/creator/campaigns", headers=a.h,
                               json={"name": "Valentine's", "channels": ["instagram"]})
    assert manual.status_code == 201
    assert len((await client.get(f"/v1/workspaces/{ws}/creator/campaigns", headers=a.h)).json()) == 2
    await client.delete(f"/v1/workspaces/{ws}/creator/campaigns/{camp['id']}", headers=a.h)
    left = (await client.get(f"/v1/workspaces/{ws}/creator/calendar?start=2027-01-01&end=2027-01-31", headers=a.h)).json()
    assert len(left) == 2 and all(i["campaign_id"] is None for i in left)


async def test_research_and_overview(client, creator, gen, provider):
    a, ws = await creator()
    r = await gen(a, ws, kind="research", brief="Who is our audience and how do we compare with Bean Bar?", save=True)
    run = r.json()["run"]
    assert run["status"] == "succeeded" and run["saved_asset_id"]
    assert "no live web research" in r.json()["assistant_message"]["content"]
    ov = (await client.get(f"/v1/workspaces/{ws}/creator/overview", headers=a.h)).json()
    assert ov["client"]["profile_complete"] == 100 and ov["content"]["draft"] == 1
    assert ov["plan"]["code"] == "free" and ov["plan"]["free_used"] == 1
    assert ov["integrations"] == {"publishing": "requires_integration", "analytics": "youtube_only"}
    assert {c["key"]: c["done"] for c in ov["checklist"]}["first_draft"] is True
