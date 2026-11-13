"""Core workflows: conversations with the assistant, saved outputs with versions, profiles, pagination."""


async def test_conversation_round_trip_saves_messages_usage_and_asset(client, signup, make_workspace, owner_db):
    a = await signup("Ada")
    ws = await make_workspace(a)
    conv = (await client.post(f"/v1/workspaces/{ws}/conversations", headers=a.h, json={"title": "Thursday ideas"})).json()
    r = await client.post(f"/v1/workspaces/{ws}/conversations/{conv['id']}/messages", headers=a.h,
                          json={"content": "Two Instagram ideas", "save_as_asset": True, "asset_type": "post"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user_message"]["role"] == "user"
    assert body["assistant_message"]["content"].startswith("Draft reply to: Two Instagram ideas")
    asset_id = body["assistant_message"]["asset_id"]
    versions = (await client.get(f"/v1/workspaces/{ws}/assets/{asset_id}/versions", headers=a.h)).json()
    assert versions[0]["source"] == "ai" and versions[0]["version"] == 1
    msgs = (await client.get(f"/v1/workspaces/{ws}/conversations/{conv['id']}/messages", headers=a.h)).json()["data"]
    assert [m["role"] for m in msgs] == ["assistant", "user"]  # newest first
    rec = owner_db.execute("SELECT agent, status, workspace_id, counted_free, run_id::text FROM ai_usage_records "
                           "ORDER BY created_at").fetchall()
    wsid = __import__("uuid").UUID(ws)
    run_id = body["run"]["id"]
    # one request = router call + agent call, linked to one run; only the final call counts against Free
    assert rec == [("router", "succeeded", wsid, False, run_id), ("creator.assistant", "succeeded", wsid, True, run_id)]
    assert body["run"]["agent"] == "creator.assistant" and body["run"]["status"] == "succeeded"


async def test_history_is_sent_in_order(client, signup, make_workspace, provider, activate_plan):
    a = await signup("Ada")
    await activate_plan(a.org_id)
    ws = await make_workspace(a)
    conv = (await client.post(f"/v1/workspaces/{ws}/conversations", headers=a.h, json={})).json()["id"]
    for t in ("first", "second", "third"):
        await client.post(f"/v1/workspaces/{ws}/conversations/{conv}/messages", headers=a.h, json={"content": t})
    req = provider.sent_to("creator.assistant")[-1]
    sent = [m.content for m in req.messages]
    assert sent[:4] == ["first", "Draft reply to: first", "second", "Draft reply to: second"]
    assert sent[4].endswith("## User request\nthird") and len(sent) == 5
    assert "Creator & Marketing" in req.system


async def test_asset_versions_and_status(client, signup, make_workspace):
    a = await signup("Ada")
    ws = await make_workspace(a)
    asset = (await client.post(f"/v1/workspaces/{ws}/assets", headers=a.h,
                               json={"type": "thread", "title": "Roast Tuesdays", "body": {"posts": ["a"]},
                                     "tags": ["roast", " "]})).json()
    assert asset["tags"] == ["roast"] and asset["current_version"] == 1
    v2 = await client.post(f"/v1/workspaces/{ws}/assets/{asset['id']}/versions", headers=a.h, json={"body": {"posts": ["b"]}})
    assert v2.status_code == 201 and v2.json()["version"] == 2
    got = (await client.get(f"/v1/workspaces/{ws}/assets/{asset['id']}", headers=a.h)).json()
    assert got["current_version"] == 2
    assert (await client.patch(f"/v1/workspaces/{ws}/assets/{asset['id']}", headers=a.h,
                               json={"status": "posted"})).json()["status"] == "posted"
    assert len((await client.get(f"/v1/workspaces/{ws}/assets?tag=roast", headers=a.h)).json()["data"]) == 1
    assert (await client.delete(f"/v1/workspaces/{ws}/assets/{asset['id']}", headers=a.h)).status_code == 204
    assert (await client.get(f"/v1/workspaces/{ws}/assets", headers=a.h)).json()["data"] == []


async def test_cursor_pagination(client, signup, make_workspace):
    a = await signup("Ada")
    ws = await make_workspace(a)
    for i in range(23):
        await client.post(f"/v1/workspaces/{ws}/assets", headers=a.h, json={"type": "note", "title": f"n{i}", "body": {}})
    seen, cursor, pages = [], None, 0
    while True:
        url = f"/v1/workspaces/{ws}/assets?limit=10" + (f"&cursor={cursor}" if cursor else "")
        page = (await client.get(url, headers=a.h)).json()
        seen += [x["id"] for x in page["data"]]
        pages += 1
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert pages == 3 and len(seen) == 23 == len(set(seen))
    r = await client.get(f"/v1/workspaces/{ws}/assets?cursor=garbage", headers=a.h)
    assert r.status_code == 400 and r.json()["code"] == "invalid_cursor"
    r = await client.get(f"/v1/workspaces/{ws}/assets?limit=500", headers=a.h)
    assert r.status_code == 400 and r.json()["code"] == "invalid_limit"


async def test_division_profiles_are_versioned(client, signup, make_workspace, activate_plan):
    a = await signup("Ada", product="business")
    ws = await make_workspace(a, "Mama Nkechi's Kitchen", product="business")
    body = {"business_name": "Mama Nkechi's Kitchen", "industry": "food", "primary_goal": "sales",
            "offers": [{"name": "Small chops tray", "price": "[YOUR PRICE]"}]}
    r1 = await client.put(f"/v1/workspaces/{ws}/business-profile", headers=a.h, json=body)
    assert r1.status_code == 200 and r1.json()["version"] == 1
    r2 = await client.put(f"/v1/workspaces/{ws}/business-profile", headers=a.h, json={**body, "budget_band": "low"})
    assert r2.json()["version"] == 2 and r2.json()["budget_band"] == "low"
    bad = await client.put(f"/v1/workspaces/{ws}/business-profile", headers=a.h, json={**body, "primary_goal": "fame"})
    assert bad.status_code == 422


async def test_workspace_creation_requires_product_access(client, signup):
    a = await signup("Ada", product="creator")
    r = await client.post(f"/v1/orgs/{a.org_id}/workspaces", headers=a.h, json={"name": "x", "product": "business"})
    assert r.status_code == 403 and r.json()["code"] == "product_not_enabled"
