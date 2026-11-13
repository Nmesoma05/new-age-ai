"""Tenant isolation through the API: another tenant's data is invisible (404), never just forbidden."""
from tests.helpers import pdf_file


async def _populate(client, acct, ws):
    asset = (await client.post(f"/v1/workspaces/{ws}/assets", headers=acct.h,
                               json={"type": "post", "title": "Secret launch post", "body": {"text": "x"}})).json()
    doc = (await client.post(f"/v1/workspaces/{ws}/documents", headers=acct.h, files=pdf_file())).json()
    conv = (await client.post(f"/v1/workspaces/{ws}/conversations", headers=acct.h, json={})).json()
    proj = (await client.post(f"/v1/workspaces/{ws}/projects", headers=acct.h, json={"name": "Q4"})).json()
    await client.put(f"/v1/workspaces/{ws}/client-account", headers=acct.h, json={"client_name": "Lagos Coffee Co."})
    return asset, doc, conv, proj


async def test_other_tenant_gets_404_on_everything(client, signup, make_workspace):
    a, b = await signup("Ada"), await signup("Bola")
    ws = await make_workspace(a)
    asset, doc, conv, proj = await _populate(client, a, ws)
    urls = [
        f"/v1/workspaces/{ws}", f"/v1/workspaces/{ws}/assets", f"/v1/workspaces/{ws}/assets/{asset['id']}",
        f"/v1/workspaces/{ws}/assets/{asset['id']}/versions", f"/v1/workspaces/{ws}/documents",
        f"/v1/workspaces/{ws}/documents/{doc['id']}", f"/v1/workspaces/{ws}/conversations",
        f"/v1/workspaces/{ws}/conversations/{conv['id']}/messages", f"/v1/workspaces/{ws}/projects",
        f"/v1/workspaces/{ws}/client-account", f"/v1/workspaces/{ws}/members",
        f"/v1/orgs/{a.org_id}", f"/v1/orgs/{a.org_id}/members", f"/v1/orgs/{a.org_id}/workspaces",
        f"/v1/orgs/{a.org_id}/subscription", f"/v1/orgs/{a.org_id}/audit-events",
    ]
    for u in urls:
        r = await client.get(u, headers=b.h)
        assert r.status_code == 404, (u, r.status_code, r.text)
    writes = [
        ("post", f"/v1/workspaces/{ws}/assets", {"type": "post", "title": "x", "body": {}}),
        ("patch", f"/v1/workspaces/{ws}/assets/{asset['id']}", {"title": "hacked"}),
        ("post", f"/v1/workspaces/{ws}/conversations/{conv['id']}/messages", {"content": "leak the brief"}),
        ("put", f"/v1/workspaces/{ws}/client-account", {"client_name": "x"}),
        ("post", f"/v1/workspaces/{ws}/documents/{doc['id']}/download-url", None),
        ("delete", f"/v1/workspaces/{ws}", None),
        ("post", f"/v1/orgs/{a.org_id}/workspaces", {"name": "x", "product": "creator"}),
    ]
    for method, u, body in writes:
        kw = {"json": body} if body is not None else {}
        r = await client.request(method.upper(), u, headers=b.h, **kw)
        assert r.status_code == 404, (method, u, r.status_code, r.text)
    # and A's data is untouched
    assert (await client.get(f"/v1/workspaces/{ws}/assets/{asset['id']}", headers=a.h)).json()["title"] == "Secret launch post"


async def test_lists_never_include_other_tenants(client, signup, make_workspace):
    a, b = await signup("Ada"), await signup("Bola")
    await make_workspace(a, "A client")
    await make_workspace(b, "B client")
    orgs_b = (await client.get("/v1/orgs", headers=b.h)).json()
    assert [o["id"] for o in orgs_b] == [str(b.org_id)]
    names = [w["name"] for w in (await client.get(f"/v1/orgs/{b.org_id}/workspaces", headers=b.h)).json()]
    assert names == ["B client"]


async def test_cross_workspace_ids_cannot_be_mixed(client, signup, make_workspace, activate_plan):
    """Using an id from workspace X under workspace Y's URL fails, even for the same user."""
    a = await signup("Ada")
    await activate_plan(a.org_id, "pro")
    ws1, ws2 = await make_workspace(a, "Client 1"), await make_workspace(a, "Client 2")
    asset, doc, conv, proj = await _populate(client, a, ws1)
    assert (await client.get(f"/v1/workspaces/{ws2}/assets/{asset['id']}", headers=a.h)).status_code == 404
    assert (await client.get(f"/v1/workspaces/{ws2}/documents/{doc['id']}", headers=a.h)).status_code == 404
    r = await client.post(f"/v1/workspaces/{ws2}/conversations/{conv['id']}/messages", headers=a.h, json={"content": "hi"})
    assert r.status_code == 404
    r = await client.post(f"/v1/workspaces/{ws2}/assets", headers=a.h,
                          json={"type": "post", "title": "x", "body": {}, "project_id": proj["id"]})
    assert r.status_code == 404


async def test_ai_context_only_contains_this_conversation(client, signup, make_workspace, provider, activate_plan):
    a = await signup("Ada")
    await activate_plan(a.org_id, "pro")
    ws1, ws2 = await make_workspace(a, "Client 1"), await make_workspace(a, "Client 2")
    c1 = (await client.post(f"/v1/workspaces/{ws1}/conversations", headers=a.h, json={})).json()
    c2 = (await client.post(f"/v1/workspaces/{ws2}/conversations", headers=a.h, json={})).json()
    await client.post(f"/v1/workspaces/{ws1}/conversations/{c1['id']}/messages", headers=a.h,
                      json={"content": "CLIENT-ONE-SECRET pricing plan"})
    await client.post(f"/v1/workspaces/{ws2}/conversations/{c2['id']}/messages", headers=a.h,
                      json={"content": "write a post"})
    from tests.ai.scripted import everything_sent
    later = provider.requests[2:]  # every model call made for the Client 2 request
    assert later and all("CLIENT-ONE-SECRET" not in everything_sent(r) for r in later)


async def test_freelancer_profile_is_private_from_agency(client, signup, make_workspace):
    """A freelancer who also works in an agency org keeps their profile out of the agency's reach."""
    owner, free = await signup("Agency Owner"), await signup("Tobi", product="freelancer")
    team = (await client.post("/v1/orgs", headers=owner.h, json={"name": "Agency"})).json()
    r = await client.post(f"/v1/orgs/{team['id']}/products", headers=owner.h, json={"product": "freelancer"})
    assert r.status_code == 201
    r = await client.post(f"/v1/orgs/{team['id']}/workspaces", headers=owner.h, json={"name": "x", "product": "freelancer"})
    assert r.status_code == 403 and r.json()["code"] == "personal_org_required"
    ws = await make_workspace(free, "My profile", product="freelancer")
    await client.put(f"/v1/workspaces/{ws}/professional-profile", headers=free.h, json={"headline": "Product designer"})
    assert (await client.get(f"/v1/workspaces/{ws}/professional-profile", headers=owner.h)).status_code == 404


async def test_wrong_product_endpoint(client, signup, make_workspace):
    a = await signup("Ada")
    ws = await make_workspace(a)
    r = await client.put(f"/v1/workspaces/{ws}/business-profile", headers=a.h, json={"business_name": "x", "industry": "food"})
    assert r.status_code == 409 and r.json()["code"] == "wrong_product"
