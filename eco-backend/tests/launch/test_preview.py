"""Preview mode (ENV=preview): a private online preview with uploads and email off and sign-up by invite only.

It is a deployed environment (https, docs hidden, AI budget and prices required) and keeps every other guard.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import get_settings
from scripts.render_start import app_url
from tests.helpers import pdf_file
from tests.launch.test_launch import _settings

PREVIEW = dict(env="preview", uploads_enabled=False, storage_backend="local", file_scanner="disabled_dev_only",
               email_backend="none", smtp_host=None, smtp_password=None, email_from=None,
               signup_allowlist=["stephen@example.com"], paystack_secret_key=None)


def test_preview_config_is_accepted_and_deployed():
    s = _settings(**PREVIEW)
    assert s.is_deployed and not s.uploads_enabled


@pytest.mark.parametrize("over,msg", [
    ({"signup_allowlist": []}, "SIGNUP_ALLOWLIST"),
    ({"uploads_enabled": True}, "STORAGE_BACKEND"),                    # uploads on need real storage...
    ({"uploads_enabled": True, "storage_backend": "s3"}, "scanning"),  # ...and a virus scanner
    ({"email_backend": "dev_outbox"}, "EMAIL_BACKEND"),
    ({"public_web_url": "http://x.onrender.com"}, "https"),
    ({"ai_daily_budget_usd": 0}, "AI_DAILY_BUDGET_USD"),
    ({"ai_model_prices": {}}, "AI_MODEL_PRICES"),
    ({"legal_terms_version": None}, "LEGAL_TERMS_VERSION"),
    ({"paystack_secret_key": "sk_live_abc"}, "LIVE key"),
])
def test_unsafe_preview_config_refused(over, msg):
    with pytest.raises(ValidationError) as e:
        _settings(**{**PREVIEW, **over})
    assert msg in str(e.value)


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_preview_relaxations_do_not_leak_into_staging_or_prod(env):
    for over in ({"uploads_enabled": False, "storage_backend": "local"},
                 {"uploads_enabled": False, "file_scanner": "disabled_dev_only"},
                 {"email_backend": "none"}):
        with pytest.raises(ValidationError):
            _settings(env=env, **over)


async def test_signup_allowlist(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "signup_allowlist", ["stephen@example.com"])
    body = {"password": "correct-horse-battery", "display_name": "S"}
    r = await client.post("/v1/auth/signup", json={**body, "email": "stranger@example.com"})
    assert r.status_code == 403 and r.json()["code"] == "signup_closed"
    r = await client.post("/v1/auth/signup", json={**body, "email": "Stephen@Example.com"})  # case-insensitive
    assert r.status_code == 201, r.text


async def test_uploads_off_refuses_with_a_clear_message(client, signup, make_workspace, monkeypatch, owner_db):
    a = await signup("Ada")
    ws = await make_workspace(a)
    monkeypatch.setattr(get_settings(), "uploads_enabled", False)
    r = await client.post(f"/v1/workspaces/{ws}/documents", headers=a.h, files=pdf_file("cv.pdf"))
    assert r.status_code == 503 and r.json()["code"] == "uploads_disabled"
    assert "turned off" in r.json()["detail"]
    assert owner_db.execute("SELECT count(*) FROM documents").fetchone()[0] == 0  # nothing stored


async def test_ready_checks_only_the_database_when_uploads_are_off(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "uploads_enabled", False)
    monkeypatch.setattr(s, "file_scanner", "clamav")
    monkeypatch.setattr(s, "clamav_port", 9)  # a scanner that is down does not matter when uploads are off
    r = await client.get("/ready")
    assert r.status_code == 200 and r.json()["checks"] == {"database": True}


def test_app_url_swaps_in_the_app_role_and_escapes_the_password():
    u = app_url("postgresql://owner:ownpw@dpg-abc-a.frankfurt-postgres.render.com:5432/neaai?sslmode=require",
                "a+b/c=d&e?f@g")
    assert u == ("postgresql+psycopg://eco_app:a%2Bb%2Fc%3Dd%26e%3Ff%40g@dpg-abc-a.frankfurt-postgres.render.com:5432"
                 "/neaai?sslmode=require")
    assert "owner" not in u and "ownpw" not in u
    assert app_url("postgres://o:p@dpg-x/db", "pw") == "postgresql+psycopg://eco_app:pw@dpg-x/db"


def test_blank_api_key_means_not_configured():
    s = _settings(**PREVIEW, openai_api_key="  ")
    assert s.openai_api_key is None  # the provider then reports "provider_not_configured" instead of calling out
