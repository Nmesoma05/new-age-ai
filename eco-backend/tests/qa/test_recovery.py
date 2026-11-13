"""Account recovery (QA BUG-03). Email is captured by the dev outbox; nothing is sent."""
import re

import pytest
from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.db import transaction
from app.models import EmailOutbox


async def _link_for(email: str) -> str | None:
    async with transaction(None, context="system") as s:
        rows = (await s.execute(select(EmailOutbox).where(EmailOutbox.to_email == email)
                                .order_by(EmailOutbox.id.desc()))).scalars().all()
    if not rows:
        return None
    return re.search(r"#token=([\w-]+)", rows[0].body).group(1)


async def test_full_reset_flow_signs_out_everywhere(client, signup):
    a = await signup("Ada")
    r = await client.post("/v1/auth/password/forgot", json={"email": a.email.upper()})
    assert r.status_code == 202 and "If an account exists" in r.json()["message"]
    token = await _link_for(a.email)
    assert token and len(token) >= 40
    old_access = a.h
    ok = await client.post("/v1/auth/password/reset", json={"token": token, "new_password": "brand-new-pass-42"})
    assert ok.status_code == 200, ok.text
    # old access token, old refresh token and old password all stop working at once
    assert (await client.get("/v1/me", headers=old_access)).status_code == 401
    assert (await client.post("/v1/auth/refresh", json={"refresh_token": a.refresh})).status_code == 401
    assert (await client.post("/v1/auth/login", json={"email": a.email, "password": "correct-horse-battery"})
            ).status_code == 401
    new = await client.post("/v1/auth/login", json={"email": a.email, "password": "brand-new-pass-42"})
    assert new.status_code == 200
    assert (await client.get("/v1/me", headers={"authorization": f"Bearer {new.json()['access_token']}"})
            ).status_code == 200
    # single use
    again = await client.post("/v1/auth/password/reset", json={"token": token, "new_password": "another-pass-77"})
    assert again.status_code == 400 and again.json()["code"] == "reset_link_invalid"


async def test_unknown_email_gets_identical_answer_and_no_mail(client, signup):
    a = await signup("Ada")
    known = await client.post("/v1/auth/password/forgot", json={"email": a.email})
    unknown = await client.post("/v1/auth/password/forgot", json={"email": "nobody-here@example.com"})
    assert known.status_code == unknown.status_code == 202 and known.json() == unknown.json()
    assert await _link_for("nobody-here@example.com") is None


async def test_expired_forged_and_throttled(client, signup, owner_db):
    a = await signup("Ada")
    for _ in range(5):
        r = await client.post("/v1/auth/password/forgot", json={"email": a.email})
        assert r.status_code == 202
    async with transaction(None, context="system") as s:
        sent = (await s.execute(text("SELECT count(*) FROM email_outbox WHERE to_email = :e"), {"e": a.email})).scalar()
    assert sent == get_settings().password_reset_max_per_hour  # capped, answer unchanged
    token = await _link_for(a.email)
    with owner_db.cursor() as c:
        c.execute("UPDATE password_reset_tokens SET expires_at = now() - interval '1 second'")
    r = await client.post("/v1/auth/password/reset", json={"token": token, "new_password": "brand-new-pass-42"})
    assert r.status_code == 400
    r = await client.post("/v1/auth/password/reset", json={"token": "x" * 43, "new_password": "brand-new-pass-42"})
    assert r.status_code == 400
    r = await client.post("/v1/auth/password/reset", json={"token": token, "new_password": "short"})
    assert r.status_code == 422


async def test_reset_clears_lockout(client, signup):
    a = await signup("Ada")
    for _ in range(get_settings().login_max_failures):
        await client.post("/v1/auth/login", json={"email": a.email, "password": "wrong-password-x"})
    locked = await client.post("/v1/auth/login", json={"email": a.email, "password": "correct-horse-battery"})
    assert locked.status_code == 429
    await client.post("/v1/auth/password/forgot", json={"email": a.email})
    await client.post("/v1/auth/password/reset", json={"token": await _link_for(a.email),
                                                      "new_password": "brand-new-pass-42"})
    assert (await client.post("/v1/auth/login", json={"email": a.email, "password": "brand-new-pass-42"})
            ).status_code == 200


async def test_change_password_keeps_this_device_and_revokes_others(client, signup):
    a = await signup("Ada")
    other = await client.post("/v1/auth/login", json={"email": a.email, "password": "correct-horse-battery"})
    wrong = await client.post("/v1/me/password", headers=a.h, json={"current_password": "nope-nope-nope",
                                                                   "new_password": "brand-new-pass-42"})
    assert wrong.status_code == 400
    r = await client.post("/v1/me/password", headers=a.h, json={"current_password": "correct-horse-battery",
                                                               "new_password": "brand-new-pass-42"})
    assert r.status_code == 200, r.text
    fresh = {"authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    assert (await client.get("/v1/me", headers=fresh)).status_code == 200
    assert (await client.post("/v1/auth/refresh", json={"refresh_token": other.json()["refresh_token"]})
            ).status_code == 401


async def test_without_email_backend_says_so(client, signup, monkeypatch):
    a = await signup("Ada")
    monkeypatch.setattr(get_settings(), "email_backend", "none")
    r = await client.post("/v1/auth/password/forgot", json={"email": a.email})
    assert r.status_code == 503 and r.json()["code"] == "email_not_configured"
    assert await _link_for(a.email) is None


@pytest.mark.parametrize("env", ["prod"])
async def test_dev_outbox_refused_in_prod(monkeypatch, env):
    from app.services import mailer
    monkeypatch.setattr(get_settings(), "env", env)
    assert mailer.available() is False
