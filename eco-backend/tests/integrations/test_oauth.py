"""OAuth connect/complete/refresh/revoke for YouTube, through the real API and database."""
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, text

from app.core import crypto
from app.core.config import get_settings
from app.core.db import transaction
from app.models import AuditEvent, Integration, IntegrationCall


async def _row(iid) -> Integration:
    async with transaction(None, context="system") as s:
        return await s.get(Integration, iid)


@pytest.fixture
def creator(signup, make_workspace):
    async def _c(name="Ada"):
        a = await signup(name)
        return a, await make_workspace(a, "Ada Cooks", "creator")
    return _c


async def test_catalog_separates_implemented_and_planned(client, signup):
    a = await signup()
    r = await client.get("/v1/integrations/catalog", headers=a.h)
    b = r.json()
    impl = {i["key"] for i in b["implemented"]}
    assert impl == {"fx_exchangerate_api", "remotive", "youtube"}
    assert "instagram" in {i["key"] for i in b["planned"]} and all(i["status"] == "planned" for i in b["planned"])
    yt = next(i for i in b["implemented"] if i["key"] == "youtube")
    assert yt["configured"] is False  # no Google client configured in tests (without the fake fixture)
    r = await client.get("/v1/integrations/catalog?product=freelancer", headers=a.h)
    assert {i["key"] for i in r.json()["implemented"]} == {"fx_exchangerate_api", "remotive"}


async def test_connect_flow_pkce_tokens_never_exposed(client, creator, fake, connect_youtube):
    a, ws = await creator()
    r = await client.post(f"/v1/workspaces/{ws}/integrations/youtube/connect", headers=a.h, json={"return_to": "/x"})
    q = parse_qs(urlsplit(r.json()["authorization_url"]).query)
    assert q["access_type"] == ["offline"] and q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == ["http://localhost:3000/integrations/callback"]
    assert set(q["scope"][0].split()) == {"https://www.googleapis.com/auth/youtube.readonly",
                                         "https://www.googleapis.com/auth/yt-analytics.readonly"}
    state, code = fake.approve(r.json()["authorization_url"])
    r = await client.post("/v1/integrations/oauth/complete", headers=a.h, json={"state": state, "code": code})
    assert r.status_code == 200, r.text
    conn = r.json()["connection"]
    assert r.json()["return_to"] == "/x"
    assert conn["status"] == "connected" and conn["account_label"] == "Ada Cooks"
    assert conn["external_account_id"] == "UC_test_channel"
    assert "ya29" not in r.text and "refresh" not in r.text
    listed = await client.get(f"/v1/workspaces/{ws}/integrations", headers=a.h)
    assert "ya29" not in listed.text and listed.json()["connections"][0]["id"] == conn["id"]
    row = await _row(conn["id"])
    assert b"ya29" not in bytes(row.encrypted_credentials)  # encrypted at rest
    assert crypto.decrypt_json(row.encrypted_credentials)["refresh_token"].startswith("1//refresh")
    # the state is single use
    again = await client.post("/v1/integrations/oauth/complete", headers=a.h, json={"state": state, "code": code})
    assert again.status_code == 400 and again.json()["code"] == "state_used"
    # reconnecting the same channel updates the one row
    await connect_youtube(a, ws)
    assert len((await client.get(f"/v1/workspaces/{ws}/integrations", headers=a.h)).json()["connections"]) == 1
    async with transaction(None, context="system") as s:
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "integration.connected"))).scalars().all()
        logs = (await s.execute(select(IntegrationCall))).scalars().all()
    assert len(ev) == 2 and "ya29" not in str(ev[0].metadata_)
    assert all("token" not in (c.path or "").replace("/token", "") for c in logs)


async def test_state_must_match_user_and_be_fresh(client, creator, signup, fake, owner_db):
    a, ws = await creator()
    other = await signup("Mallory")
    url = (await client.post(f"/v1/workspaces/{ws}/integrations/youtube/connect", headers=a.h, json={})).json()
    state, code = fake.approve(url["authorization_url"])
    r = await client.post("/v1/integrations/oauth/complete", headers=other.h, json={"state": state, "code": code})
    assert r.status_code == 400 and r.json()["code"] == "bad_state"
    url = (await client.post(f"/v1/workspaces/{ws}/integrations/youtube/connect", headers=a.h, json={})).json()
    state, code = fake.approve(url["authorization_url"])
    with owner_db.cursor() as c:
        c.execute("UPDATE oauth_states SET expires_at = now() - interval '1 minute' WHERE used_at IS NULL")
    r = await client.post("/v1/integrations/oauth/complete", headers=a.h, json={"state": state, "code": code})
    assert r.status_code == 400 and r.json()["code"] == "state_expired"
    # user pressed Cancel at Google
    url = (await client.post(f"/v1/workspaces/{ws}/integrations/youtube/connect", headers=a.h, json={})).json()
    state, _ = fake.approve(url["authorization_url"])
    r = await client.post("/v1/integrations/oauth/complete", headers=a.h, json={"state": state, "error": "access_denied"})
    assert r.status_code == 400 and r.json()["code"] == "access_denied"
    assert (await client.get(f"/v1/workspaces/{ws}/integrations", headers=a.h)).json()["connections"] == []


async def test_wrong_verifier_and_missing_scopes(client, creator, fake):
    a, ws = await creator()
    url = (await client.post(f"/v1/workspaces/{ws}/integrations/youtube/connect", headers=a.h, json={})).json()
    state, code = fake.approve(url["authorization_url"])
    fake.challenges[code] = "not-the-challenge"  # a stolen code without our verifier is useless
    r = await client.post("/v1/integrations/oauth/complete", headers=a.h, json={"state": state, "code": code})
    assert r.status_code == 502 and r.json()["code"] == "bad_request"
    fake.token_scope = "https://www.googleapis.com/auth/youtube.readonly"  # user unticked analytics
    url = (await client.post(f"/v1/workspaces/{ws}/integrations/youtube/connect", headers=a.h, json={})).json()
    state, code = fake.approve(url["authorization_url"])
    r = await client.post("/v1/integrations/oauth/complete", headers=a.h, json={"state": state, "code": code})
    assert r.status_code == 400 and r.json()["code"] == "scopes_missing"
    assert (await client.get(f"/v1/workspaces/{ws}/integrations", headers=a.h)).json()["connections"] == []


async def test_only_org_admins_connect_and_planned_or_unconfigured_refused(client, creator, signup, fake, activate_plan):
    owner = await signup("Owner")
    org = (await client.post("/v1/orgs", headers=owner.h, json={"name": "Agency"})).json()["id"]
    await activate_plan(org, "team")
    await client.post(f"/v1/orgs/{org}/products", headers=owner.h, json={"product": "creator"})
    ed = await signup("Editor")
    assert (await client.post(f"/v1/orgs/{org}/members", headers=owner.h,
                              json={"email": ed.email, "role": "member"})).status_code == 201
    ws = (await client.post(f"/v1/orgs/{org}/workspaces", headers=owner.h,
                            json={"name": "Client", "product": "creator"})).json()["id"]
    await client.post(f"/v1/workspaces/{ws}/members", headers=owner.h, json={"user_id": str(ed.user_id), "role": "editor"})
    r = await client.post(f"/v1/workspaces/{ws}/integrations/youtube/connect", headers=ed.h, json={})
    assert r.status_code == 403
    r = await client.post(f"/v1/workspaces/{ws}/integrations/instagram/connect", headers=owner.h, json={})
    assert r.status_code == 409 and r.json()["code"] == "integration_planned"
    r = await client.post(f"/v1/workspaces/{ws}/integrations/youtube/connect", headers=owner.h,
                          json={"return_to": "//evil.example"})
    assert r.status_code == 422
    get_settings().google_oauth_client_id = None
    r = await client.post(f"/v1/workspaces/{ws}/integrations/youtube/connect", headers=owner.h, json={})
    assert r.status_code == 503 and r.json()["code"] == "not_configured"


async def test_refresh_then_invalid_grant_needs_reauth(client, creator, fake, connect_youtube, owner_db):
    a, ws = await creator()
    conn = await connect_youtube(a, ws)
    with owner_db.cursor() as c:
        c.execute("UPDATE integrations SET token_expires_at = now() - interval '1 minute'")
    r = await client.post(f"/v1/workspaces/{ws}/integrations/{conn['id']}/sync", headers=a.h, json={})
    assert r.status_code == 200, r.text
    row = await _row(conn["id"])
    creds = crypto.decrypt_json(row.encrypted_credentials)
    assert creds["access_token"].startswith("ya29.refreshed") and creds["refresh_token"].startswith("1//refresh")
    assert row.token_expires_at > datetime.now(UTC) + timedelta(minutes=50)
    # provider down during refresh: old token kept, failure recorded, nothing marked synced
    fake.refresh_mode = "down"
    with owner_db.cursor() as c:
        c.execute("UPDATE integrations SET token_expires_at = now() - interval '1 minute'")
    r = await client.post(f"/v1/workspaces/{ws}/integrations/{conn['id']}/sync", headers=a.h, json={})
    assert r.status_code == 502 and r.json()["retryable"] is True
    row2 = await _row(conn["id"])
    assert row2.status == "connected" and row2.consecutive_failures == 1 and row2.last_error
    assert crypto.decrypt_json(row2.encrypted_credentials) == creds
    # the user revoked access at Google
    fake.refresh_mode = "invalid_grant"
    r = await client.post(f"/v1/workspaces/{ws}/integrations/{conn['id']}/sync", headers=a.h, json={})
    assert r.status_code == 409 and r.json()["code"] == "needs_reauth"
    assert (await _row(conn["id"])).status == "needs_reauth"
    r = await client.post(f"/v1/workspaces/{ws}/integrations/{conn['id']}/sync", headers=a.h, json={})
    assert r.status_code == 409  # no provider call is even attempted now
    # reconnecting fixes it
    fake.refresh_mode = "ok"
    again = await connect_youtube(a, ws)
    assert again["id"] == conn["id"] and again["status"] == "connected"


async def test_key_rotation(client, creator, fake, connect_youtube, monkeypatch):
    a, ws = await creator()
    conn = await connect_youtube(a, ws)
    old = get_settings().credentials_encryption_key.get_secret_value()
    new = Fernet.generate_key().decode()
    from pydantic import SecretStr
    monkeypatch.setattr(get_settings(), "credentials_encryption_key", SecretStr(f"{new},{old}"))
    crypto._keys.cache_clear()
    crypto._fernet.cache_clear()
    try:
        r = await client.post(f"/v1/workspaces/{ws}/integrations/{conn['id']}/sync", headers=a.h, json={})
        assert r.status_code == 200, r.text
        row = await _row(conn["id"])
        assert row.key_version == 2
        Fernet(new.encode()).decrypt(bytes(row.encrypted_credentials))  # now under the new key
    finally:
        monkeypatch.undo()
        crypto._keys.cache_clear()
        crypto._fernet.cache_clear()


async def test_disconnect_confirmed_and_unconfirmed(client, creator, fake, connect_youtube):
    a, ws = await creator()
    conn = await connect_youtube(a, ws)
    r = await client.delete(f"/v1/workspaces/{ws}/integrations/{conn['id']}", headers=a.h)
    assert r.status_code == 200 and r.json()["provider_confirmed"] is True
    row = await _row(conn["id"])
    assert row.status == "revoked" and bytes(row.encrypted_credentials) == b"\x00"
    assert fake.count("oauth2.googleapis.com", "/revoke") == 1
    r = await client.post(f"/v1/workspaces/{ws}/integrations/{conn['id']}/sync", headers=a.h, json={})
    assert r.status_code == 409 and r.json()["code"] == "revoked"
    fake.channel_id = "UC_second"
    conn2 = await connect_youtube(a, ws)
    fake.revoke_mode = "down"
    r = await client.delete(f"/v1/workspaces/{ws}/integrations/{conn2['id']}", headers=a.h)
    b = r.json()
    assert b["provider_confirmed"] is False and "myaccount.google.com/permissions" in b["message"]
    assert bytes((await _row(conn2["id"])).encrypted_credentials) == b"\x00"  # our copy is gone either way


async def test_other_tenants_cannot_see_or_touch(client, creator, fake, connect_youtube):
    a, ws = await creator()
    conn = await connect_youtube(a, ws)
    b, ws_b = await creator("Bola")
    assert (await client.get(f"/v1/workspaces/{ws}/integrations", headers=b.h)).status_code == 404
    assert (await client.post(f"/v1/workspaces/{ws_b}/integrations/{conn['id']}/sync", headers=b.h,
                              json={})).status_code == 404
    assert (await client.delete(f"/v1/workspaces/{ws_b}/integrations/{conn['id']}", headers=b.h)).status_code == 404
    assert (await client.get(f"/v1/workspaces/{ws_b}/integrations", headers=b.h)).json()["connections"] == []
    # direct DB: the app role can't read another org's integration rows
    async with transaction(b.user_id) as s:
        assert (await s.execute(text("SELECT count(*) FROM integrations"))).scalar_one() == 0
        assert (await s.execute(text("SELECT count(*) FROM oauth_states"))).scalar_one() == 0


async def test_sync_writes_metrics_once_per_day_and_detects_account_change(client, creator, fake, connect_youtube):
    a, ws = await creator()
    conn = await connect_youtube(a, ws)
    for _ in range(2):
        r = await client.post(f"/v1/workspaces/{ws}/integrations/{conn['id']}/sync", headers=a.h, json={})
        assert r.status_code == 200, r.text
    b = r.json()
    assert b["videos"] == 2 and b["subscribers"] == 1520 and b["source"] == "YouTube Analytics API"
    async with transaction(None, context="system") as s:
        pm = (await s.execute(text("SELECT post_label, video_views, source FROM post_metrics ORDER BY video_views DESC"))).all()
        fs = (await s.execute(text("SELECT followers, source FROM follower_snapshots"))).all()
        row = await s.get(Integration, conn["id"])
    assert pm == [("Jollof in 10 minutes", 1200, "integration"), ("Market day", 300, "integration")]
    assert fs == [(1520, "integration")] and row.last_sync_at is not None
    fake.channel_id = "UC_someone_else"
    r = await client.post(f"/v1/workspaces/{ws}/integrations/{conn['id']}/sync", headers=a.h, json={})
    assert r.status_code == 409 and r.json()["code"] == "account_changed"
    r = await client.post(f"/v1/workspaces/{ws}/integrations/{conn['id']}/sync", headers=a.h,
                          json={"start": "2026-01-01", "end": "2025-01-01"})
    assert r.status_code == 422
    fake.overrides[("youtubeanalytics.googleapis.com", "/v2/reports")] = httpx.Response(403)
    fake.channel_id = "UC_test_channel"
    r = await client.post(f"/v1/workspaces/{ws}/integrations/{conn['id']}/sync", headers=a.h, json={})
    assert r.status_code == 403 and r.json()["code"] == "permission_denied"
