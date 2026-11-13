"""Account recovery and password changes (QA BUG-03).

- forgot(): same response whether or not the email exists (no account enumeration) and similar work either way.
  At most N reset emails per account per hour. Tokens: 32 random bytes, only sha256 stored, 30 minutes, single use.
- reset(): sets the new password, marks the token used, invalidates every other outstanding reset token, revokes all
  refresh tokens (signs out every device), clears lockout, and stamps password_changed_at so access tokens issued
  before it stop working immediately (deps.get_principal checks `iat`).
- change(): same effects, authenticated with the current password.
- Email: only through app.services.mailer. With no email backend configured the endpoint says recovery by email is
  unavailable; it never claims a message was sent.
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.core.db import transaction
from app.core.errors import AppError
from app.core.security import hash_password, hash_token, verify_password
from app.models import PasswordResetToken, RefreshToken, User
from app.services import audit, mailer

GENERIC = ("If an account exists for that email, we've sent a link to reset the password. It works for 30 minutes "
           "and only once.")


async def forgot(email: str, request: Request) -> dict:
    s = get_settings()
    if not mailer.available():
        raise AppError(503, "email_not_configured", "Unavailable",
                       "Password reset by email isn't available on this server yet. Contact support to recover "
                       "your account.")
    now = datetime.now(UTC)
    async with transaction(None, context="system") as db:
        user = (await db.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
        if user is None or not user.is_active or user.deleted_at is not None or not user.password_hash:
            hash_password(secrets.token_urlsafe(12))  # similar work, so timing doesn't reveal the answer
            return {"message": GENERIC}
        recent = (await db.execute(select(func.count()).select_from(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id, PasswordResetToken.created_at > now - timedelta(hours=1)))).scalar_one()
        if recent >= s.password_reset_max_per_hour:
            await audit.record(db, "auth.password_reset_throttled", actor_id=None, target_type="user",
                               target_id=user.id, request=request)
            return {"message": GENERIC}  # same answer: don't reveal the throttle (it would confirm the account)
        raw = secrets.token_urlsafe(32)
        db.add(PasswordResetToken(user_id=user.id, token_hash=hash_token(raw),
                                  expires_at=now + timedelta(minutes=s.password_reset_ttl_minutes)))
        link = f"{s.public_web_url.rstrip('/')}/reset-password#token={raw}"
        await mailer.send(db, to=user.email, purpose="password_reset", subject="Reset your New Age AI password",
                          body=(f"Hi {user.display_name},\n\nSomeone (hopefully you) asked to reset your password. "
                                f"Open this link within {s.password_reset_ttl_minutes} minutes:\n\n{link}\n\n"
                                "If it wasn't you, ignore this email: your password stays the same.\n\nNew Age AI, a product of New Age Media"))
        await audit.record(db, "auth.password_reset_requested", actor_id=None, target_type="user", target_id=user.id,
                           request=request)
    return {"message": GENERIC}


async def _apply_new_password(db, user: User, new_password: str, now: datetime) -> None:
    user.password_hash = hash_password(new_password)
    user.password_changed_at = now
    user.failed_logins, user.locked_until = 0, None
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
                     .values(revoked_at=now))
    await db.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == user.id,
                                                      PasswordResetToken.used_at.is_(None)).values(used_at=now))


async def reset(token: str, new_password: str, request: Request) -> dict:
    now = datetime.now(UTC)
    async with transaction(None, context="system") as db:
        row = (await db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token))
                                .with_for_update())).scalar_one_or_none()
        if row is None or row.used_at is not None or row.expires_at <= now:
            raise AppError(400, "reset_link_invalid", "Link invalid",
                           "This reset link has expired or was already used. Ask for a new one.")
        user = await db.get(User, row.user_id, with_for_update=True)
        if user is None or not user.is_active or user.deleted_at is not None:
            raise AppError(400, "reset_link_invalid", "Link invalid", "This reset link can't be used.")
        if verify_password(new_password, user.password_hash):
            raise AppError(422, "password_reused", "Choose a new password", "Pick a password you haven't just used.")
        await _apply_new_password(db, user, new_password, now)
        await audit.record(db, "auth.password_reset", actor_id=user.id, target_type="user", target_id=user.id,
                           request=request)
    return {"message": "Password changed. Every device was signed out; sign in with the new password."}


async def change(user_id, current: str, new_password: str, request: Request) -> dict:
    now = datetime.now(UTC)
    async with transaction(None, context="system") as db:
        user = await db.get(User, user_id, with_for_update=True)
        if user is None or not verify_password(current, user.password_hash):
            raise AppError(400, "wrong_password", "Wrong password", "Your current password isn't right.")
        if current == new_password:
            raise AppError(422, "password_reused", "Choose a new password", "The new password must be different.")
        await _apply_new_password(db, user, new_password, now)
        await audit.record(db, "auth.password_changed", actor_id=user.id, target_type="user", target_id=user.id,
                           request=request)
    return {"message": "Password changed. Other devices were signed out."}
