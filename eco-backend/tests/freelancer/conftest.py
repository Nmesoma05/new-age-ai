import pytest

from tests.freelancer.helpers import PROFILE


@pytest.fixture
def fl(client, signup):
    async def _f(name="Chiamaka", **over):
        a = await signup(name, product=None)
        r = await client.post("/v1/freelancer/onboarding", headers=a.h, json={"profile": {**PROFILE, **over}})
        assert r.status_code == 201, r.text
        return a, r.json()["workspace_id"]
    return _f


@pytest.fixture
def fgen(client):
    async def _g(acct, ws, **body):
        return await client.post(f"/v1/workspaces/{ws}/freelancer/generate", headers=acct.h, json=body)
    return _g
