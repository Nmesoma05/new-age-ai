"""Workflows 5-6: approvals (team + client review links) and performance reporting with exports."""



async def _asset(client, a, ws, title="Cold brew is back", text="Iced and ready."):
    return (await client.post(f"/v1/workspaces/{ws}/assets", headers=a.h,
                              json={"type": "post", "title": title, "body": {"platform": "instagram"},
                                    "body_text": text})).json()


async def _agency(client, signup, onboard, activate_plan):
    owner, editor = await signup("Owner", product=None), await signup("Editor", product=None)
    res = await onboard(owner, mode="agency", agency_name="Agency")
    await activate_plan(res["org_id"], "team")
    await client.post(f"/v1/orgs/{res['org_id']}/members", headers=owner.h, json={"email": editor.email, "role": "member"})
    ws = res["workspace_id"]
    await client.post(f"/v1/workspaces/{ws}/members", headers=owner.h, json={"user_id": str(editor.user_id), "role": "editor"})
    return owner, editor, ws


async def test_team_review_loop(client, signup, onboard, activate_plan, owner_db):
    owner, editor, ws = await _agency(client, signup, onboard, activate_plan)
    a = await _asset(client, editor, ws)
    base = f"/v1/workspaces/{ws}/creator/assets/{a['id']}"
    assert (await client.post(base + "/submit", headers=editor.h, json={"note": "Ready for a look"})).json()["status"] == "in_review"
    r = await client.post(base + "/decision", headers=editor.h, json={"decision": "approve"})
    assert r.status_code == 403  # editors can't approve their own work
    r = await client.post(base + "/decision", headers=owner.h, json={"decision": "request_changes", "comment": "Warmer tone"})
    assert r.json()["status"] == "draft"
    await client.post(f"/v1/workspaces/{ws}/assets/{a['id']}/versions", headers=editor.h,
                      json={"body": {}, "body_text": "Iced, ready, and made with love."})
    await client.post(base + "/submit", headers=editor.h, json={})
    queue = (await client.get(f"/v1/workspaces/{ws}/creator/approvals", headers=owner.h)).json()
    assert [x["id"] for x in queue["in_review"]] == [a["id"]] and queue["can_approve"] is True
    r = await client.post(base + "/decision", headers=owner.h, json={"decision": "approve", "comment": "Lovely"})
    assert r.json()["status"] == "approved"
    await client.post(base + "/comments", headers=editor.h, json={"body": "Thanks!"})
    kinds = [(c["kind"], c["asset_version"]) for c in (await client.get(base + "/comments", headers=owner.h)).json()]
    assert kinds == [("submitted", 1), ("changes_requested", 1), ("submitted", 2), ("approved", 2), ("comment", 2)]
    acts = [r[0] for r in owner_db.execute("SELECT action FROM audit_events").fetchall()]
    assert "asset.changes_requested" in acts and "asset.approved" in acts


async def test_client_review_link(client, creator, owner_db):
    a, ws = await creator()
    one, two = await _asset(client, a, ws), await _asset(client, a, ws, "Second post", "Second text")
    hidden = await _asset(client, a, ws, "Not shared", "HIDDEN-TEXT")
    r = await client.post(f"/v1/workspaces/{ws}/creator/review-links", headers=a.h,
                          json={"asset_ids": [one["id"], two["id"]], "label": "December posts", "expires_in_days": 7})
    assert r.status_code == 201
    link = r.json()
    token = link["token"]
    stored = owner_db.execute("SELECT token_hash FROM review_links").fetchone()[0]
    assert token not in stored and len(stored) == 64
    page = await client.get(f"/v1/review/{token}")  # no Authorization header
    assert page.status_code == 200
    body = page.json()
    assert body["client"] == "Lagos Coffee Co." and [i["title"] for i in body["items"]] == ["Cold brew is back", "Second post"]
    assert "HIDDEN-TEXT" not in page.text and all(i["status"] == "in_review" for i in body["items"])
    r = await client.post(f"/v1/review/{token}/assets/{hidden['id']}", json={"decision": "approve", "name": "Tolu"})
    assert r.status_code == 404
    r = await client.post(f"/v1/review/{token}/assets/{two['id']}", json={"decision": "request_changes", "name": "Tolu"})
    assert r.status_code == 422
    r = await client.post(f"/v1/review/{token}/assets/{one['id']}", json={"decision": "approve", "name": "Tolu",
                                                                          "comment": "Perfect"})
    assert r.json()["status"] == "approved"
    r = await client.post(f"/v1/review/{token}/assets/{two['id']}", json={"decision": "request_changes", "name": "Tolu",
                                                                          "comment": "Shorter please"})
    assert r.json()["status"] == "draft"
    team_view = (await client.get(f"/v1/workspaces/{ws}/creator/assets/{one['id']}/comments", headers=a.h)).json()
    assert team_view[-1]["via"] == "client_link" and team_view[-1]["author_name"] == "Tolu"
    acts = [r[0] for r in owner_db.execute("SELECT action FROM audit_events").fetchall()]
    assert "review.client_approved" in acts and "review.client_changes_requested" in acts
    assert (await client.delete(f"/v1/workspaces/{ws}/creator/review-links/{link['id']}", headers=a.h)).status_code == 204
    assert (await client.get(f"/v1/review/{token}")).status_code == 404
    assert (await client.get("/v1/review/not-a-real-token")).status_code == 404


async def test_expired_and_comment_only_links(client, creator, owner_db):
    a, ws = await creator()
    one = await _asset(client, a, ws)
    link = (await client.post(f"/v1/workspaces/{ws}/creator/review-links", headers=a.h,
                              json={"asset_ids": [one["id"]], "label": "Look only", "allow_approve": False})).json()
    r = await client.post(f"/v1/review/{link['token']}/assets/{one['id']}", json={"decision": "approve", "name": "T"})
    assert r.status_code == 403
    owner_db.execute("UPDATE review_links SET expires_at = now() - interval '1 minute'")
    assert (await client.get(f"/v1/review/{link['token']}")).status_code == 404


async def test_review_link_rejects_foreign_assets(client, creator):
    a, ws = await creator("Ada")
    b, ws_b = await creator("Bola")
    theirs = await _asset(client, b, ws_b)
    r = await client.post(f"/v1/workspaces/{ws}/creator/review-links", headers=a.h,
                          json={"asset_ids": [theirs["id"]], "label": "x"})
    assert r.status_code == 404


async def test_metrics_report_and_exports(client, creator, gen, provider):
    a, ws = await creator()
    m = f"/v1/workspaces/{ws}/creator/metrics"
    r = await client.post(m, headers=a.h, json={"platform": "instagram", "post_label": "Roast day", "published_on": "2026-11-03",
                                                "impressions": 5100, "reach": 4000, "likes": 300, "comments": 40,
                                                "shares": 20, "saves": 60, "post_url": "https://instagram.com/p/1"})
    assert r.status_code == 201 and r.json()["source"] == "manual"
    csv_data = ("title,platform,date,impressions,likes,comments,shares,saves,clicks\n"
                "=HYPERLINK(\"https://evil.example\"),x,2026-11-05,2000,50,5,10,,12\n"
                "Morning menu,Twitter,2026-11-06,1300,30,2,1,0,\n").encode()
    r = await client.post(m + "/import", headers=a.h, files={"file": ("x.csv", csv_data, "text/csv")})
    assert r.status_code == 201 and r.json() == {"imported": 2}
    bad = b"title,platform,date,impressions\nOne,instagram,2026-11-07,lots\nTwo,myspace,2026-11-08,4\n"
    r = await client.post(m + "/import", headers=a.h, files={"file": ("bad.csv", bad, "text/csv")})
    assert r.status_code == 422 and [e["row"] for e in r.json()["rows"]] == [2, 3]
    assert len((await client.get(m + "?start=2026-11-01&end=2026-11-30", headers=a.h)).json()) == 3  # nothing partial
    await client.put(f"/v1/workspaces/{ws}/creator/followers", headers=a.h,
                     json={"platform": "instagram", "captured_on": "2026-11-01", "followers": 1200})
    await client.put(f"/v1/workspaces/{ws}/creator/followers", headers=a.h,
                     json={"platform": "instagram", "captured_on": "2026-11-30", "followers": 1000})
    f = await client.put(f"/v1/workspaces/{ws}/creator/followers", headers=a.h,
                         json={"platform": "instagram", "captured_on": "2026-11-30", "followers": 1350})
    assert f.json()["followers"] == 1350  # same day updates, not duplicates

    rep = (await client.get(f"/v1/workspaces/{ws}/creator/report?start=2026-11-01&end=2026-11-30", headers=a.h)).json()
    t = rep["totals"]
    assert (rep["posts"], t["impressions"], t["engagements"], t["clicks"]) == (3, 8400, 518, 12)
    assert t["engagement_rate"] == round(100 * 518 / 8400, 2)
    assert [p["platform"] for p in rep["by_platform"]] == ["instagram", "x"]
    assert rep["top_posts"][0]["label"] == "Roast day" and rep["followers"][0]["change"] == 150
    assert rep["sources"] == {"manual": 1, "csv_import": 2}
    assert t["video_views"] is None and t["reach"] == 4000  # never recorded → None, not a fake 0
    assert any("haven't been verified" in c for c in rep["caveats"]) and any("missing" in c for c in rep["caveats"])

    g = await gen(a, ws, kind="report", brief="Monthly report for the client", start_date="2026-11-01",
                  end_date="2026-11-30")
    assert g.status_code == 201, g.text
    sent = provider.sent_to("creator.report_writer")[0].messages[-1].content
    assert "Impressions: 8,400" in sent and "Engagements (likes+comments+shares+saves): 518" in sent
    narrative_run = g.json()["run"]["id"]
    assert "3 posts recorded with 8,400 impressions" in g.json()["assistant_message"]["content"]

    base = f"/v1/workspaces/{ws}/creator/report/export?start=2026-11-01&end=2026-11-30"
    csv_out = await client.get(base + "&format=csv", headers=a.h)
    assert "'=HYPERLINK" in csv_out.text  # formula neutralised
    md = await client.get(base + f"&format=md&narrative_run_id={narrative_run}", headers=a.h)
    assert "They were not fetched from the platforms" in md.text and "Commentary (AI-written" in md.text
    html = await client.get(base + "&format=html", headers=a.h)
    assert html.headers["content-type"].startswith("text/html") and "<script" not in html.text
    assert '=HYPERLINK(&quot;https://evil.example&quot;)' in html.text  # user text is escaped, never markup
    assert html.headers["content-disposition"].startswith('attachment; filename="Lagos-Coffee-Co-report-2026-11-01-2026-11-30.html"')


async def test_library_export(client, creator):
    a, ws = await creator()
    await _asset(client, a, ws, "Post one", "First text")
    await _asset(client, a, ws, "=cmd()", "Second text")
    csv_ = await client.get(f"/v1/workspaces/{ws}/creator/library/export?format=csv", headers=a.h)
    assert "Post one" in csv_.text and "'=cmd()" in csv_.text
    md = await client.get(f"/v1/workspaces/{ws}/creator/library/export?format=md&status=draft", headers=a.h)
    assert md.text.startswith("# Content library") and "## Post one" in md.text


async def test_access_rules(client, signup, onboard, activate_plan, creator, make_workspace):
    owner, editor, ws = await _agency(client, signup, onboard, activate_plan)
    viewer = await signup("Viewer", product=None)
    org = (await client.get("/v1/creator/clients", headers=owner.h)).json()[0]["org_id"]
    await client.post(f"/v1/orgs/{org}/members", headers=owner.h, json={"email": viewer.email, "role": "member"})
    await client.post(f"/v1/workspaces/{ws}/members", headers=owner.h, json={"user_id": str(viewer.user_id), "role": "viewer"})
    item = {"title": "x", "platform": "x", "scheduled_for": "2026-12-01T09:00:00Z"}
    assert (await client.post(f"/v1/workspaces/{ws}/creator/calendar", headers=viewer.h, json=item)).status_code == 403
    assert (await client.get(f"/v1/workspaces/{ws}/creator/overview", headers=viewer.h)).status_code == 200
    r = await client.post(f"/v1/workspaces/{ws}/creator/generate", headers=viewer.h, json={"kind": "content", "brief": "hello there"})
    assert r.status_code == 403
    stranger, other_ws = await creator("Eve")
    assert (await client.get(f"/v1/workspaces/{ws}/creator/overview", headers=stranger.h)).status_code == 404
    biz = await signup("Biz", product="business")
    bws = await make_workspace(biz, "Shop", product="business")
    r = await client.get(f"/v1/workspaces/{bws}/creator/overview", headers=biz.h)
    assert r.status_code == 409 and r.json()["code"] == "wrong_product"
