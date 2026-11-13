"""Role-based authorisation inside one organisation."""
import pytest


@pytest.fixture
def agency(client, signup, activate_plan):
    async def _setup():
        owner = await signup("Owner")
        team = (await client.post("/v1/orgs", headers=owner.h, json={"name": "Agency"})).json()
        org = team["id"]
        await activate_plan(team["id"], "team")
        await client.post(f"/v1/orgs/{org}/products", headers=owner.h, json={"product": "creator"})
        people = {}
        for name, role in [("Admin", "admin"), ("Writer", "member"), ("Viewer", "member"), ("Approver", "member"),
                           ("Finance", "billing"), ("Outsider", None)]:
            acct = await signup(name)
            if role:
                r = await client.post(f"/v1/orgs/{org}/members", headers=owner.h, json={"email": acct.email, "role": role})
                assert r.status_code == 201, r.text
            people[name] = acct
        ws_a = (await client.post(f"/v1/orgs/{org}/workspaces", headers=owner.h, json={"name": "Client A", "product": "creator"})).json()["id"]
        ws_b = (await client.post(f"/v1/orgs/{org}/workspaces", headers=owner.h, json={"name": "Client B", "product": "creator"})).json()["id"]
        for name, role in [("Writer", "editor"), ("Viewer", "viewer"), ("Approver", "client_approver")]:
            r = await client.post(f"/v1/workspaces/{ws_a}/members", headers=owner.h,
                                  json={"user_id": str(people[name].user_id), "role": role})
            assert r.status_code == 201, r.text
        return owner, org, ws_a, ws_b, people
    return _setup


async def test_workspace_roles(client, agency):
    owner, org, ws_a, ws_b, p = await agency()
    post = {"type": "post", "title": "Hello", "body": {"text": "hi"}}
    # editor writes in A, cannot see B
    assert (await client.post(f"/v1/workspaces/{ws_a}/assets", headers=p["Writer"].h, json=post)).status_code == 201
    assert (await client.get(f"/v1/workspaces/{ws_b}/assets", headers=p["Writer"].h)).status_code == 404
    # viewer reads but cannot write
    assert (await client.get(f"/v1/workspaces/{ws_a}/assets", headers=p["Viewer"].h)).status_code == 200
    r = await client.post(f"/v1/workspaces/{ws_a}/assets", headers=p["Viewer"].h, json=post)
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
    # client approver has no general workspace access
    assert (await client.get(f"/v1/workspaces/{ws_a}/assets", headers=p["Approver"].h)).status_code == 404
    # org admin is an implicit admin of every workspace
    assert (await client.get(f"/v1/workspaces/{ws_b}/assets", headers=p["Admin"].h)).status_code == 200
    # outsider sees nothing
    assert (await client.get(f"/v1/workspaces/{ws_a}", headers=p["Outsider"].h)).status_code == 404


async def test_workspace_listing_respects_membership(client, agency):
    owner, org, ws_a, ws_b, p = await agency()
    names = [w["name"] for w in (await client.get(f"/v1/orgs/{org}/workspaces", headers=p["Writer"].h)).json()]
    assert names == ["Client A"]
    names = [w["name"] for w in (await client.get(f"/v1/orgs/{org}/workspaces", headers=p["Admin"].h)).json()]
    assert names == ["Client A", "Client B"]


async def test_only_admins_approve(client, agency):
    owner, org, ws_a, ws_b, p = await agency()
    a = (await client.post(f"/v1/workspaces/{ws_a}/assets", headers=p["Writer"].h,
                           json={"type": "post", "title": "Hello", "body": {}})).json()
    r = await client.patch(f"/v1/workspaces/{ws_a}/assets/{a['id']}", headers=p["Writer"].h, json={"status": "approved"})
    assert r.status_code == 403 and r.json()["code"] == "approval_required"
    r = await client.patch(f"/v1/workspaces/{ws_a}/assets/{a['id']}", headers=owner.h, json={"status": "approved"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    # editing approved content resets it to in_review
    await client.post(f"/v1/workspaces/{ws_a}/assets/{a['id']}/versions", headers=p["Writer"].h, json={"body": {"t": 2}})
    assert (await client.get(f"/v1/workspaces/{ws_a}/assets/{a['id']}", headers=owner.h)).json()["status"] == "in_review"


async def test_org_role_matrix(client, agency):
    owner, org, ws_a, ws_b, p = await agency()
    new = {"email": p["Outsider"].email, "role": "member"}
    assert (await client.post(f"/v1/orgs/{org}/members", headers=p["Writer"].h, json=new)).status_code == 403
    assert (await client.get(f"/v1/orgs/{org}/audit-events", headers=p["Writer"].h)).status_code == 403
    assert (await client.get(f"/v1/orgs/{org}/audit-events", headers=p["Admin"].h)).status_code == 200
    assert (await client.get(f"/v1/orgs/{org}/subscription", headers=p["Finance"].h)).status_code == 200
    assert (await client.get(f"/v1/orgs/{org}/subscription", headers=p["Writer"].h)).status_code == 403
    assert (await client.post(f"/v1/orgs/{org}/workspaces", headers=p["Writer"].h,
                              json={"name": "x", "product": "creator"})).status_code == 403
    assert (await client.post(f"/v1/orgs/{org}/members", headers=p["Admin"].h, json=new)).status_code == 201


async def test_owner_is_protected(client, agency):
    owner, org, ws_a, ws_b, p = await agency()
    r = await client.delete(f"/v1/orgs/{org}/members/{owner.user_id}", headers=p["Admin"].h)
    assert r.status_code == 403 and r.json()["code"] == "owner_protected"
    r = await client.delete(f"/v1/workspaces/{ws_a}", headers=p["Admin"].h)
    assert r.status_code == 403  # only the owner deletes workspaces


async def test_removing_org_member_removes_workspace_access(client, agency):
    owner, org, ws_a, ws_b, p = await agency()
    assert (await client.get(f"/v1/workspaces/{ws_a}", headers=p["Writer"].h)).status_code == 200
    assert (await client.delete(f"/v1/orgs/{org}/members/{p['Writer'].user_id}", headers=owner.h)).status_code == 204
    assert (await client.get(f"/v1/workspaces/{ws_a}", headers=p["Writer"].h)).status_code == 404


async def test_personal_org_cannot_add_members(client, signup):
    a, b = await signup("Ada"), await signup("Bola")
    r = await client.post(f"/v1/orgs/{a.org_id}/members", headers=a.h, json={"email": b.email, "role": "member"})
    assert r.status_code == 403 and r.json()["code"] == "personal_org"


async def test_teams(client, agency):
    owner, org, ws_a, ws_b, p = await agency()
    t = await client.post(f"/v1/orgs/{org}/teams", headers=owner.h, json={"name": "Content"})
    assert t.status_code == 201
    r = await client.post(f"/v1/orgs/{org}/teams/{t.json()['id']}/members", headers=owner.h,
                          json={"user_id": str(p["Writer"].user_id)})
    assert r.status_code == 204
    r = await client.post(f"/v1/orgs/{org}/teams/{t.json()['id']}/members", headers=owner.h,
                          json={"user_id": str(p["Outsider"].user_id)})
    assert r.status_code == 422 and r.json()["code"] == "not_org_member"
    assert (await client.post(f"/v1/orgs/{org}/teams", headers=p["Writer"].h, json={"name": "X"})).status_code == 403
