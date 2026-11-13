import pytest

from tests.business.helpers import BIZ


@pytest.fixture
def biz_onboard(client):
    async def _on(acct, mode="solo", team_name=None, **profile):
        body = {"mode": mode, "profile": {**BIZ, **profile}}
        if team_name:
            body["team_name"] = team_name
        r = await client.post("/v1/business/onboarding", headers=acct.h, json=body)
        assert r.status_code == 201, r.text
        return r.json()
    return _on


@pytest.fixture
def biz(signup, biz_onboard):
    async def _b(name="Ada", **profile):
        a = await signup(name, product=None)
        res = await biz_onboard(a, **profile)
        return a, res["workspace_id"]
    return _b


@pytest.fixture
def bgen(client):
    async def _g(acct, ws, **body):
        return await client.post(f"/v1/workspaces/{ws}/business/generate", headers=acct.h, json=body)
    return _g
