"""Launch readiness: readiness probe, deployed-environment guards, AI spend cap, SMTP email, terms acceptance,
data export, account deletion + purge, S3 storage."""
import json
import subprocess
import sys
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings, get_settings
from tests.helpers import pdf_file

# ---------------------------------------------------------------- readiness


async def test_health_and_ready(client):
    h = await client.get("/health")
    assert h.status_code == 200 and h.json()["status"] == "ok" and "release" in h.json()
    r = await client.get("/ready")
    assert r.status_code == 200, r.text
    assert r.json()["checks"] == {"database": True, "storage": True, "scanner": True}


async def test_ready_fails_when_schema_is_behind(client, owner_db):
    owner_db.execute("UPDATE alembic_version SET version_num = '0008_account_recovery'")
    try:
        r = await client.get("/ready")
        assert r.status_code == 503 and r.json()["checks"]["database"] is False
    finally:
        owner_db.execute("UPDATE alembic_version SET version_num = '0009_launch'")


async def test_ready_fails_when_scanner_is_down(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "file_scanner", "clamav")
    monkeypatch.setattr(s, "clamav_host", "127.0.0.1")
    monkeypatch.setattr(s, "clamav_port", 9)  # nothing listens
    r = await client.get("/ready")
    assert r.status_code == 503 and r.json()["checks"] == {"database": True, "storage": True, "scanner": False}
    assert "Traceback" not in r.text


# ---------------------------------------------------------------- deployed guards
BASE = dict(database_url="postgresql+psycopg://u:p@h/db", jwt_secret="x" * 40,
            credentials_encryption_key="k", file_scanner="clamav", embedding_provider="openai",
            storage_backend="s3", email_backend="smtp", smtp_host="smtp.example.com", smtp_password="pw",
            email_from="Eco <no-reply@example.com>", public_web_url="https://app.example.com",
            cors_origins=["https://app.example.com"], ai_daily_budget_usd=50.0, legal_terms_version="2026-11-13",
            ai_model="model-a", ai_model_prices={"model-a": [0.15, 0.6]},
            ai_price_in_per_1m_usd=0.0, ai_price_out_per_1m_usd=0.0)  # no fallback: each model needs its price


def _settings(**over):
    key = "sk_live_x" if over.get("env") == "prod" else "sk_test_x"  # the right key unless a case overrides it
    return Settings(_env_file=None, **{**BASE, "paystack_secret_key": key, **over})


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_good_deployed_config_is_accepted(env):
    pk = "sk_live_x" if env == "prod" else "sk_test_x"
    assert _settings(env=env, paystack_secret_key=pk).is_deployed


@pytest.mark.parametrize("env,over,msg", [
    ("prod", {"paystack_secret_key": "sk_test_abc"}, "TEST key"),
    ("staging", {"paystack_secret_key": "sk_live_abc"}, "LIVE key"),
    ("prod", {"storage_backend": "local"}, "STORAGE_BACKEND"),
    ("staging", {"email_backend": "dev_outbox"}, "EMAIL_BACKEND"),
    ("prod", {"public_web_url": "http://app.example.com"}, "https"),
    ("prod", {"cors_origins": ["*"]}, "https"),
    ("prod", {"ai_daily_budget_usd": 0}, "AI_DAILY_BUDGET_USD"),
    ("staging", {"legal_terms_version": None}, "LEGAL_TERMS_VERSION"),
    ("staging", {"file_scanner": "disabled_dev_only"}, "scanning"),
    ("prod", {"ai_model_prices": {}}, "AI_MODEL_PRICES"),
    ("prod", {"ai_model_fast": "model-b"}, "AI_MODEL_PRICES for model-b"),
])
def test_unsafe_deployed_config_refused(env, over, msg):
    with pytest.raises(ValidationError) as e:
        _settings(env=env, **over)
    assert msg in str(e.value)


def test_docs_hidden_when_deployed(monkeypatch):
    from app.main import create_app
    monkeypatch.setattr(get_settings(), "env", "staging")
    assert create_app().docs_url is None


# ---------------------------------------------------------------- AI spend cap
async def test_daily_ai_budget_pauses_generation(client, signup, make_workspace, owner_db, monkeypatch, caplog):
    a = await signup()
    ws = await make_workspace(a)
    conv = (await client.post(f"/v1/workspaces/{ws}/conversations", headers=a.h, json={})).json()["id"]
    monkeypatch.setattr(get_settings(), "ai_daily_budget_usd", 10.0)
    owner_db.execute("INSERT INTO ai_usage_records (org_id, user_id, agent, model, status, tokens_in, tokens_out, "
                     "cost_usd, counted_free, latency_ms) VALUES (%s, %s, 'x', 'm', 'succeeded', 1, 1, 8.5, false, 1)",
                     (a.org_id, a.user_id))
    ok = await client.post(f"/v1/workspaces/{ws}/conversations/{conv}/messages", headers=a.h, json={"content": "Hi"})
    assert ok.status_code == 201  # 85%: still allowed, alert logged
    assert any("budget alert" in r.getMessage() for r in caplog.records)
    owner_db.execute("UPDATE ai_usage_records SET cost_usd = 10 WHERE agent = 'x'")
    r = await client.post(f"/v1/workspaces/{ws}/conversations/{conv}/messages", headers=a.h, json={"content": "Hi"})
    assert r.status_code == 503 and r.json()["code"] == "ai_paused"
    assert 0 < int(r.headers["retry-after"]) <= 86401
    # someone else, other org, same platform cap
    b = await signup("Bola")
    wb = await make_workspace(b)
    cb = (await client.post(f"/v1/workspaces/{wb}/conversations", headers=b.h, json={})).json()["id"]
    assert (await client.post(f"/v1/workspaces/{wb}/conversations/{cb}/messages", headers=b.h,
                              json={"content": "Hi"})).status_code == 503


# ---------------------------------------------------------------- SMTP email
class FakeSMTP:
    sent: list = []
    tls = False

    def __init__(self, host, port, timeout):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context):
        FakeSMTP.tls = True

    def login(self, u, p):
        assert p == "smtp-pass"

    def send_message(self, msg):
        assert FakeSMTP.tls, "must not send before STARTTLS"
        FakeSMTP.sent.append(msg)


async def test_password_reset_sends_by_smtp_and_stores_nothing(client, signup, monkeypatch, owner_db):
    import app.services.mailer as mailer
    a = await signup()
    s = get_settings()
    for k, v in {"email_backend": "smtp", "smtp_host": "smtp.example.com", "smtp_username": "apikey",
                 "smtp_password": SecretStr("smtp-pass"), "email_from": "Eco <no-reply@example.com>"}.items():
        monkeypatch.setattr(s, k, v)
    FakeSMTP.sent, FakeSMTP.tls = [], False
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    r = await client.post("/v1/auth/password/forgot", json={"email": a.email})
    assert r.status_code == 202
    assert len(FakeSMTP.sent) == 1 and FakeSMTP.sent[0]["To"] == a.email
    assert "/reset-password#token=" in FakeSMTP.sent[0].get_content()
    assert owner_db.execute("SELECT count(*) FROM email_outbox").fetchone()[0] == 0  # the link isn't stored


async def test_smtp_failure_does_not_change_the_answer(client, signup, monkeypatch, caplog):
    import app.services.mailer as mailer
    a = await signup()
    s = get_settings()
    for k, v in {"email_backend": "smtp", "smtp_host": "smtp.example.com", "email_from": "x@example.com"}.items():
        monkeypatch.setattr(s, k, v)

    def boom(*a, **k):
        raise OSError("connection refused")
    monkeypatch.setattr(mailer.smtplib, "SMTP", boom)
    known = await client.post("/v1/auth/password/forgot", json={"email": a.email})
    unknown = await client.post("/v1/auth/password/forgot", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 202 and known.json() == unknown.json()
    assert any(r.getMessage() == "email delivery failed" for r in caplog.records)


# ---------------------------------------------------------------- terms acceptance
async def test_signup_requires_current_terms_when_configured(client, monkeypatch, owner_db):
    monkeypatch.setattr(get_settings(), "legal_terms_version", "2026-11-13")
    body = {"email": "t@example.com", "password": "correct-horse-battery", "display_name": "T"}
    r = await client.post("/v1/auth/signup", json=body)
    assert r.status_code == 422 and r.json()["code"] == "terms_required"
    r = await client.post("/v1/auth/signup", json={**body, "accept_terms": True})
    assert r.status_code == 201
    v, at = owner_db.execute("SELECT terms_version, terms_accepted_at FROM users WHERE email='t@example.com'").fetchone()
    assert v == "2026-11-13" and at is not None


# ---------------------------------------------------------------- export
async def test_export_contains_my_data_and_no_secrets(client, signup, make_workspace):
    a = await signup("Ada Export")
    ws = await make_workspace(a)
    conv = (await client.post(f"/v1/workspaces/{ws}/conversations", headers=a.h, json={})).json()["id"]
    await client.post(f"/v1/workspaces/{ws}/conversations/{conv}/messages", headers=a.h, json={"content": "Hello export"})
    await client.post(f"/v1/workspaces/{ws}/documents", headers=a.h, files=pdf_file("brief.pdf"))
    r = await client.get("/v1/me/export", headers=a.h)
    assert r.status_code == 200 and r.headers["content-disposition"].startswith("attachment;")
    d = r.json()
    assert d["account"]["email"] == a.email and "password_hash" not in d["account"]
    assert any(m["content"] == "Hello export" for c in d["conversations"] for m in c["messages"])
    assert any(m["role"] == "assistant" for c in d["conversations"] for m in c["messages"])
    assert d["documents"][0]["filename"] == "brief.pdf" and "storage_key" not in d["documents"][0]
    for bad in ("password_hash", "token_hash", "encrypted_credentials", "argon2"):
        assert bad not in r.text
    # someone else's export never has my data
    b = await signup("Bola")
    assert "Hello export" not in (await client.get("/v1/me/export", headers=b.h)).text


# ---------------------------------------------------------------- deletion + purge
def _purge(*args):
    return subprocess.run([sys.executable, "-m", "scripts.purge_deleted", *args], capture_output=True, text=True,
                          env={**__import__("os").environ}, timeout=60)


async def test_delete_account_then_purge(client, signup, make_workspace, owner_db):
    a = await signup("Del Me")
    ws = await make_workspace(a)
    up = await client.post(f"/v1/workspaces/{ws}/documents", headers=a.h, files=pdf_file("cv.pdf"))
    assert up.status_code == 201
    wrong = await client.post("/v1/me/delete", headers=a.h, json={"password": "nope-nope-nope", "confirm": "DELETE"})
    assert wrong.status_code == 400 and wrong.json()["code"] == "wrong_password"
    no_word = await client.post("/v1/me/delete", headers=a.h, json={"password": "correct-horse-battery", "confirm": "yes"})
    assert no_word.status_code == 422
    r = await client.post("/v1/me/delete", headers=a.h, json={"password": "correct-horse-battery", "confirm": "DELETE"})
    assert r.status_code == 200, r.text
    # signed out everywhere, can't sign in, the old token is dead
    assert (await client.get("/v1/me", headers=a.h)).status_code == 401
    assert (await client.post("/v1/auth/login", json={"email": a.email, "password": "correct-horse-battery"})).status_code == 401
    assert (await client.post("/v1/auth/refresh", json={"refresh_token": a.refresh})).status_code == 401
    email, name, ph = owner_db.execute("SELECT email, display_name, password_hash FROM users WHERE id=%s", (a.user_id,)).fetchone()
    assert email.endswith("@deleted.invalid") and name == "Deleted user" and ph is None
    assert owner_db.execute("SELECT count(*) FROM workspaces WHERE id=%s AND deleted_at IS NOT NULL", (ws,)).fetchone()[0] == 1
    # the email can be used again for a new account
    assert (await client.post("/v1/auth/signup", json={"email": a.email, "password": "correct-horse-battery",
                                                       "display_name": "New"})).status_code == 201
    key = owner_db.execute("SELECT storage_key FROM documents WHERE workspace_id=%s", (ws,)).fetchone()[0]
    from app.services.storage import get_storage
    assert await get_storage().get(key)  # still there during the grace period
    dry = _purge("--days", "30")
    assert "0 organisation" in dry.stdout, dry.stdout + dry.stderr
    owner_db.execute("UPDATE organisations SET deleted_at = now() - interval '31 days' WHERE id=%s", (a.org_id,))
    plan = _purge()
    assert "would erase" in plan.stdout and owner_db.execute("SELECT count(*) FROM workspaces WHERE id=%s", (ws,)).fetchone()[0] == 1
    done = _purge("--apply")
    assert "erased" in done.stdout and "1 file" in done.stdout, done.stdout + done.stderr
    assert owner_db.execute("SELECT count(*) FROM workspaces WHERE id=%s", (ws,)).fetchone()[0] == 0
    assert owner_db.execute("SELECT count(*) FROM documents WHERE workspace_id=%s", (ws,)).fetchone()[0] == 0
    with pytest.raises(FileNotFoundError):
        await get_storage().get(key)
    assert owner_db.execute("SELECT count(*) FROM audit_events WHERE action='org.purged'").fetchone()[0] == 1


async def test_delete_refused_while_owning_a_used_team_or_renewing_plan(client, signup, activate_plan, owner_db):
    owner = await signup("Owner")
    org = (await client.post("/v1/orgs", headers=owner.h, json={"name": "Agency"})).json()["id"]
    await activate_plan(org, "team")
    m = await signup("Member")
    await client.post(f"/v1/orgs/{org}/members", headers=owner.h, json={"email": m.email, "role": "member"})
    r = await client.post("/v1/me/delete", headers=owner.h, json={"password": "correct-horse-battery", "confirm": "DELETE"})
    assert r.status_code == 409 and r.json()["code"] == "transfer_ownership_first" and r.json()["organisations"] == ["Agency"]
    solo = await signup("Solo")
    await activate_plan(solo.org_id, "pro")
    owner_db.execute("UPDATE subscriptions SET auto_renew = true WHERE org_id = %s", (solo.org_id,))
    r = await client.post("/v1/me/delete", headers=solo.h, json={"password": "correct-horse-battery", "confirm": "DELETE"})
    assert r.status_code == 409 and r.json()["code"] == "cancel_subscription_first"
    # the member (not an owner) can delete; the agency keeps working
    r = await client.post("/v1/me/delete", headers=m.h, json={"password": "correct-horse-battery", "confirm": "DELETE"})
    assert r.status_code == 200
    members = (await client.get(f"/v1/orgs/{org}/members", headers=owner.h)).json()
    assert [x["display_name"] for x in members] == ["Owner"]


# ---------------------------------------------------------------- S3 storage (moto)
async def test_s3_storage_roundtrip_and_prefix_delete(monkeypatch):
    moto = pytest.importorskip("moto")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with moto.mock_aws():
        import boto3

        from app.services.storage import S3Storage
        boto3.client("s3").create_bucket(Bucket="eco-files")
        st = S3Storage("eco-files", None)
        await st.put("org/a/ws/1/doc", b"hello")
        await st.put("org/a/ws/2/doc", b"x")
        await st.put("org/b/ws/3/doc", b"keep")
        assert await st.get("org/a/ws/1/doc") == b"hello"
        head = boto3.client("s3").head_object(Bucket="eco-files", Key="org/a/ws/1/doc")
        assert head["ServerSideEncryption"] == "AES256"
        assert await st.delete_prefix("org/a/") == 2
        assert await st.get("org/b/ws/3/doc") == b"keep"
        await st.delete("org/b/ws/3/doc")
        assert boto3.client("s3").list_objects_v2(Bucket="eco-files").get("KeyCount") == 0
    assert datetime.now(UTC)  # keep import used
    assert json


# ---------------------------------------------------------------- logs
def test_json_log_lines_carry_request_id_and_redact():
    import logging

    from app.core.observability import JsonFormatter, request_id_var
    tok = request_id_var.set("req-123")
    try:
        rec = logging.LogRecord("eco.access", logging.INFO, __file__, 1, "request", None, None)
        rec.method, rec.path, rec.status, rec.email, rec.password = "GET", "/v1/me", 200, "a@b.c", "hunter2"
        line = json.loads(JsonFormatter().format(rec))
    finally:
        request_id_var.reset(tok)
    assert line["request_id"] == "req-123" and line["status"] == 200 and line["env"] == get_settings().env
    assert line["email"] == "[redacted]" and line["password"] == "[redacted]"
    assert "hunter2" not in json.dumps(line)


async def test_request_log_has_no_query_string(client, caplog):
    import logging
    caplog.set_level(logging.INFO, logger="eco.access")
    await client.get("/v1/me?token=SECRET123")
    lines = [r for r in caplog.records if r.name == "eco.access"]
    assert lines and lines[-1].path == "/v1/me" and all("SECRET123" not in str(vars(r)) for r in lines)
    from app.core.observability import JsonFormatter
    assert json.loads(JsonFormatter().format(lines[-1]))["request_id"]  # the line carries its request id


# ---------------------------------------------------------------- limits shared across workers/instances
async def test_ip_limit_is_shared_between_app_instances(client, signup, monkeypatch):
    import httpx

    from app.main import create_app
    monkeypatch.setattr(get_settings(), "login_ip_max_failures", 2)
    a = await signup()
    xff = {"x-forwarded-for": "203.0.113.77"}
    for _ in range(2):  # two failures on instance 1
        assert (await client.post("/v1/auth/login", headers=xff, json={"email": a.email, "password": "wrong-pass-1"})).status_code == 401
    other = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://t")
    async with other:  # a second, independent app instance (another worker or server)
        r = await other.post("/v1/auth/login", headers=xff, json={"email": a.email, "password": "correct-horse-battery"})
    assert r.status_code == 429


# ---------------------------------------------------------------- virus scanner protocol (BUG-15)
@pytest.mark.parametrize("reply,want", [
    (b"stream: OK\0", "clean"), (b"stream: OK\n", "clean"),
    (b"stream: Eicar-Signature FOUND\0", "rejected"),
    (b"INSTREAM size limit exceeded. ERROR\0", "pending"), (b"", "pending"),
])
def test_clamd_reply_parsing(reply, want):
    from app.services.storage import parse_clamd_reply
    assert parse_clamd_reply(reply) == want


async def test_scan_against_a_clamd_speaking_server(monkeypatch):
    """A socket server speaking clamd's z-mode protocol, replying in two packets like a real network can."""
    import asyncio
    import struct

    from app.services import storage

    async def handle(r, w):
        await r.readexactly(len(b"zINSTREAM\0"))
        body = b""
        while True:
            n = struct.unpack("!L", await r.readexactly(4))[0]
            if n == 0:
                break
            body += await r.readexactly(n)
        verdict = b"stream: Eicar-Test-Signature FOUND\0" if b"EICAR" in body else b"stream: OK\0"
        w.write(verdict[:5])
        await w.drain()
        await asyncio.sleep(0.05)
        w.write(verdict[5:])
        await w.drain()
        w.close()
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    s = get_settings()
    monkeypatch.setattr(s, "file_scanner", "clamav")
    monkeypatch.setattr(s, "clamav_host", "127.0.0.1")
    monkeypatch.setattr(s, "clamav_port", port)
    async with server:
        assert await storage.scan(b"%PDF-1.4 a clean file" * 5000) == "clean"
        assert await storage.scan(b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!") == "rejected"


async def test_manual_plan_activation_script(client, signup, owner_db):
    a = await signup()
    r = subprocess.run([sys.executable, "-m", "scripts.activate_plan", "--org", str(a.org_id), "--plan", "pro",
                        "--days", "30", "--ref", "INV-001", "--by", "Ops"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "pro active" in r.stdout, r.stderr
    assert (await client.get(f"/v1/orgs/{a.org_id}/subscription", headers=a.h)).json()["ai_unlimited"] is True
    meta = owner_db.execute("SELECT metadata FROM audit_events WHERE action='billing.manual_activation'").fetchone()[0]
    assert meta["ref"] == "INV-001" and meta["by"] == "Ops"


def test_every_setting_is_documented_in_env_example():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[2] / ".env.example").read_text().upper()
    missing = [f for f in Settings.model_fields if f.upper() not in text]
    assert missing == [], f"add these to .env.example: {missing}"
