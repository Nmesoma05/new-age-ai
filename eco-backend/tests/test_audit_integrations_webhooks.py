import hashlib
import hmac
import json
import os


async def test_important_actions_are_audited(client, signup, make_workspace):
    a = await signup("Ada")
    ws = await make_workspace(a)
    await client.post(f"/v1/workspaces/{ws}/assets", headers=a.h, json={"type": "post", "title": "x", "body": {}})
    events = (await client.get(f"/v1/orgs/{a.org_id}/audit-events", headers=a.h)).json()["data"]
    actions = [e["action"] for e in events]
    assert actions[:3] == ["asset.created", "workspace.created", "account.signup"]
    assert all(e["actor_user_id"] == str(a.user_id) for e in events[:3])


async def test_integration_credentials_encrypted_and_never_returned(client, signup, owner_db):
    a = await signup("Ada")
    r = await client.post(f"/v1/orgs/{a.org_id}/integrations", headers=a.h,
                          json={"provider": "example_crm", "account_label": "Main", "scopes": ["read"],
                                "credentials": {"api_key": "sk_live_SUPERSECRET"}})
    assert r.status_code == 201
    assert "SUPERSECRET" not in r.text and "credentials" not in r.json()
    listed = await client.get(f"/v1/orgs/{a.org_id}/integrations", headers=a.h)
    assert "SUPERSECRET" not in listed.text
    blob = bytes(owner_db.execute("SELECT encrypted_credentials FROM integrations").fetchone()[0])
    assert b"SUPERSECRET" not in blob
    from app.core.crypto import decrypt_json
    assert decrypt_json(blob) == {"api_key": "sk_live_SUPERSECRET"}
    audit = owner_db.execute("SELECT metadata::text FROM audit_events WHERE action = 'integration.connected'").fetchone()[0]
    assert "SUPERSECRET" not in audit
    assert (await client.delete(f"/v1/orgs/{a.org_id}/integrations/{r.json()['id']}", headers=a.h)).status_code == 204
    assert bytes(owner_db.execute("SELECT encrypted_credentials FROM integrations").fetchone()[0]) == b"\x00"


def _sign(body: bytes) -> str:
    return hmac.new(os.environ["PAYSTACK_SECRET_KEY"].encode(), body, hashlib.sha512).hexdigest()


async def test_payment_webhook_signature_and_idempotency(client, signup, owner_db):
    a = await signup("Ada")
    payload = {"event": "charge.success", "data": {"reference": "ref_123", "authorization": {"reusable": False},
                                                   "metadata": {"org_id": str(a.org_id), "plan_code": "pro",
                                                                "period_days": 30}}}
    body = json.dumps(payload).encode()
    bad = await client.post("/v1/webhooks/paystack", content=body, headers={"x-paystack-signature": "0" * 128})
    assert bad.status_code == 401
    ok = await client.post("/v1/webhooks/paystack", content=body, headers={"x-paystack-signature": _sign(body)})
    assert ok.status_code == 200 and ok.json()["status"] == "processed"
    dup = await client.post("/v1/webhooks/paystack", content=body, headers={"x-paystack-signature": _sign(body)})
    assert dup.json()["status"] == "duplicate"
    sub = (await client.get(f"/v1/orgs/{a.org_id}/subscription", headers=a.h)).json()
    assert sub["plan"] == "pro" and sub["auto_renew"] is False
    assert owner_db.execute("SELECT count(*) FROM subscriptions").fetchone()[0] == 1
