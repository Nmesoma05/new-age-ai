import pytest

PROFILE = {"client_name": "Lagos Coffee Co.", "industry": "Food & drink", "website": "https://lagoscoffee.example",
           "business_info": {"description": "Specialty coffee bar in Victoria Island",
                             "offers": [{"name": "Cold brew", "price": "NGN 4,500"}], "location": "Lagos"},
           "platforms": ["instagram", "x"], "brand_voice": {"tone": "warm, witty"},
           "audience": {"summary": "Young professionals on the Island"},
           "goals": [{"goal": "More weekday morning orders", "metric": "orders before 10am"}],
           "competitors": [{"name": "Bean Bar", "handle": "@beanbar", "platform": "instagram",
                            "notes": "Mostly product photos"}],
           "content_pillars": [{"name": "Craft", "purpose": "How it's made", "example_topics": ["roasting"]}]}


@pytest.fixture
def onboard(client):
    async def _on(acct, mode="solo", agency_name=None, **profile):
        body = {"mode": mode, "client": {**PROFILE, **profile}}
        if agency_name:
            body["agency_name"] = agency_name
        r = await client.post("/v1/creator/onboarding", headers=acct.h, json=body)
        assert r.status_code == 201, r.text
        return r.json()
    return _on


@pytest.fixture
def creator(signup, onboard):
    async def _c(name="Ada"):
        a = await signup(name, product=None)
        res = await onboard(a)
        return a, res["workspace_id"]
    return _c


@pytest.fixture
def gen(client):
    async def _g(acct, ws, **body):
        r = await client.post(f"/v1/workspaces/{ws}/creator/generate", headers=acct.h, json=body)
        return r
    return _g
