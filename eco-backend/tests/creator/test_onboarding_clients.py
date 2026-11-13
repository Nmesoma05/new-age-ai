"""Workflow 1: onboarding and multi-client workspaces."""
from tests.creator.conftest import PROFILE


async def test_solo_onboarding(client, signup, onboard, owner_db):
    a = await signup("Ada", product=None)
    state = (await client.get("/v1/creator/onboarding", headers=a.h)).json()
    assert state["next_step"] == "create_first_client" and state["clients"] == []
    res = await onboard(a)
    assert res["org_id"] == str(a.org_id)
    state = (await client.get("/v1/creator/onboarding", headers=a.h)).json()
    assert state["next_step"] == "done"
    c = state["clients"][0]
    assert c["client_name"] == "Lagos Coffee Co." and c["role"] == "admin" and c["profile_complete"] == 100
    prof = (await client.get(f"/v1/workspaces/{res['workspace_id']}/client-account", headers=a.h)).json()
    assert prof["competitors"][0]["name"] == "Bean Bar" and prof["business_info"]["offers"][0]["price"] == "NGN 4,500"
    acts = [r[0] for r in owner_db.execute("SELECT action FROM audit_events ORDER BY id").fetchall()]
    assert "org.product_enrolled" in acts and "workspace.created" in acts


async def test_free_plan_allows_one_client_and_says_so(client, signup, onboard):
    a = await signup("Ada", product=None)
    await onboard(a)
    r = await client.post("/v1/creator/clients", headers=a.h, json={"org_id": str(a.org_id),
                                                                    "client": {**PROFILE, "client_name": "Second"}})
    assert r.status_code == 402 and r.json()["code"] == "workspace_limit_reached"


async def test_agency_with_isolated_clients(client, signup, onboard, activate_plan, gen, provider):
    a = await signup("Ada", product=None)
    res = await onboard(a, mode="agency", agency_name="Ada Social", client_name="Client One",
                        brand_voice={"secret": "CLIENT-ONE-VOICE"})
    await activate_plan(res["org_id"], "team")
    r = await client.post("/v1/creator/clients", headers=a.h, json={
        "org_id": res["org_id"], "client": {**PROFILE, "client_name": "Client Two", "brand_voice": {"tone": "bold"}}})
    assert r.status_code == 201
    ws2 = r.json()["workspace_id"]
    listed = (await client.get("/v1/creator/clients", headers=a.h)).json()
    assert [c["client_name"] for c in listed] == ["Client One", "Client Two"]
    assert all(c["org_name"] == "Ada Social" for c in listed)
    from tests.ai.scripted import call
    provider.on("creator.content_writer", call("get_profile", {}, ("search_context", {"query": "voice", "sources": "all"})))
    r = await gen(a, ws2, kind="content", brief="Two posts for the weekend", count=2)
    assert r.status_code == 201, r.text
    from tests.ai.scripted import everything_sent
    assert all("CLIENT-ONE-VOICE" not in everything_sent(q) for q in provider.requests)


async def test_only_org_admins_add_clients(client, signup, onboard, activate_plan):
    owner, member = await signup("Owner", product=None), await signup("Member", product=None)
    res = await onboard(owner, mode="agency", agency_name="Agency")
    await activate_plan(res["org_id"], "team")
    await client.post(f"/v1/orgs/{res['org_id']}/members", headers=owner.h, json={"email": member.email, "role": "member"})
    r = await client.post("/v1/creator/clients", headers=member.h, json={"org_id": res["org_id"], "client": PROFILE})
    assert r.status_code == 403
    stranger = await signup("Eve", product=None)
    r = await client.post("/v1/creator/clients", headers=stranger.h, json={"org_id": res["org_id"], "client": PROFILE})
    assert r.status_code == 404


async def test_profile_validation(client, signup):
    a = await signup("Ada", product=None)
    bad = {"mode": "solo", "client": {**PROFILE, "website": "javascript:alert(1)"}}
    assert (await client.post("/v1/creator/onboarding", headers=a.h, json=bad)).status_code == 422
    bad = {"mode": "solo", "client": {**PROFILE, "platforms": ["myspace"]}}
    assert (await client.post("/v1/creator/onboarding", headers=a.h, json=bad)).status_code == 422
    assert (await client.post("/v1/creator/onboarding", headers=a.h,
                              json={"mode": "agency", "client": PROFILE})).status_code == 422


async def test_capabilities_are_honest(client):
    caps = (await client.get("/v1/creator/capabilities")).json()
    status = {f["feature"]: f["status"] for f in caps["features"]}
    assert status["Publishing / scheduling to platforms"] == "requires_integration"
    assert status["Automatic analytics import"] == "partial"  # YouTube only, after connecting
    assert status["Performance reporting"] == "manual"
    assert all(p["publishing"] == "requires_integration" for p in caps["platforms"])
    assert {p["platform"] for p in caps["platforms"] if p["analytics"] != "requires_integration"} == {"youtube"}
