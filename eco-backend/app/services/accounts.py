"""Account lifecycle: sign-up, personal organisation, sessions."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import set_tenant, system_context, transaction
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    verify_password,
)
from app.models import Organisation, OrgMember, ProductAccess, RefreshToken, User
from app.services import audit


async def create_personal_org(session: AsyncSession, user: User, product: str | None) -> Organisation:
    org = Organisation(name=f"{user.display_name}'s workspace", kind="personal", owner_user_id=user.id)
    session.add(org)
    await session.flush()
    session.add(OrgMember(org_id=org.id, user_id=user.id, role="owner"))
    if product:
        session.add(ProductAccess(org_id=org.id, product=product, status="active"))
    await session.flush()
    return org


async def signup(session: AsyncSession, *, email: str, password: str, display_name: str, country: str | None,
                 currency: str | None, product: str | None, request: Request,
                 accept_terms: bool = False) -> tuple[User, Organisation]:
    allow = [] if get_settings().signup_open else get_settings().signup_allowlist
    if allow and email.lower() not in {a.strip().lower() for a in allow}:
        raise AppError(403, "signup_closed", "Sign-up is invite-only",
                       "This preview is private. Ask the New Age AI team for an invite.")
    terms = get_settings().legal_terms_version
    if terms and not accept_terms:
        raise AppError(422, "terms_required", "Accept the terms to continue",
                       "Read and accept the Terms of Service and Privacy Policy to create an account.")
    async with system_context(session):
        exists = (await session.execute(select(User.id).where(User.email == email))).scalar_one_or_none()
        if exists:
            # Same generic response whether or not the email exists would need an email round-trip;
            # until email verification ships, a 409 is returned and the event is audited.
            raise AppError(409, "email_in_use", "Email already registered",
                           "Sign in instead, or reset your password.")
        user = User(email=email, password_hash=hash_password(password), display_name=display_name,
                    country=country, currency=currency, terms_version=terms,
                    terms_accepted_at=datetime.now(UTC) if terms else None)
        session.add(user)
        await session.flush()
    await set_tenant(session, user.id)
    org = await create_personal_org(session, user, product)
    await audit.record(session, "account.signup", actor_id=user.id, org_id=org.id, target_type="user",
                       target_id=user.id, metadata={"product": product}, request=request)
    return user, org


async def issue_tokens(session: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID | None = None,
                       user_agent: str | None = None) -> dict:
    s = get_settings()
    raw, digest = new_refresh_token()
    async with system_context(session, user_id):
        rt = RefreshToken(user_id=user_id, family_id=family_id or uuid.uuid4(), token_hash=digest,
                          expires_at=datetime.now(UTC) + timedelta(days=s.refresh_token_ttl_days),
                          user_agent=(user_agent or "")[:300])
        session.add(rt)
        await session.flush()
    access, ttl = create_access_token(user_id)
    return {"access_token": access, "token_type": "bearer", "expires_in": ttl, "refresh_token": raw,
            "_refresh_id": rt.id}


async def login(session: AsyncSession, *, email: str, password: str, request: Request) -> dict:
    s = get_settings()
    now = datetime.now(UTC)
    async with system_context(session):
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user and user.locked_until and user.locked_until > now:
            raise AppError(429, "account_locked", "Too many attempts",
                           "Too many failed sign-ins. Try again later or reset your password.")
        ok = verify_password(password, user.password_hash if user else None)
        if not ok or user is None or not user.is_active or user.deleted_at is not None:
            if user is not None:
                # Separate transaction: the failure count and audit row must persist although we raise.
                async with transaction(None, context="system") as s2:
                    u = await s2.get(User, user.id, with_for_update=True)
                    u.failed_logins += 1
                    if u.failed_logins >= s.login_max_failures:
                        u.locked_until = now + timedelta(minutes=s.login_lockout_minutes)
                        u.failed_logins = 0
                    await audit.record(s2, "auth.login_failed", actor_id=None, target_type="user",
                                       target_id=user.id, request=request)
            raise AppError(401, "invalid_credentials", "Unauthenticated", "Email or password is incorrect.")
        user.failed_logins = 0
        user.locked_until = None
        await audit.record(session, "auth.login", actor_id=user.id, target_type="user", target_id=user.id,
                           request=request)
    tokens = await issue_tokens(session, user.id, user_agent=request.headers.get("user-agent"))
    tokens.pop("_refresh_id")
    return tokens


async def refresh(session: AsyncSession, raw: str, request: Request) -> dict:
    now = datetime.now(UTC)
    async with system_context(session):
        rt = (await session.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)))
              ).scalar_one_or_none()
        if rt is None or rt.expires_at <= now:
            raise AppError(401, "invalid_refresh_token", "Unauthenticated", "Sign in again.")
        if rt.revoked_at is not None:
            # Reuse of a rotated token: assume theft and revoke the whole family (own transaction, so it
            # persists although we raise).
            async with transaction(None, context="system") as s2:
                await s2.execute(update(RefreshToken).where(RefreshToken.family_id == rt.family_id,
                                                            RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
                await audit.record(s2, "auth.refresh_reuse_detected", actor_id=None, target_type="user",
                                   target_id=rt.user_id, request=request)
            raise AppError(401, "invalid_refresh_token", "Unauthenticated", "Sign in again.")
        rt.revoked_at = now
        user_id, family = rt.user_id, rt.family_id
    tokens = await issue_tokens(session, user_id, family, request.headers.get("user-agent"))
    async with system_context(session):
        rt.replaced_by = tokens.pop("_refresh_id")
    return tokens


async def logout(session: AsyncSession, raw: str) -> None:
    async with system_context(session):
        rt = (await session.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)))
              ).scalar_one_or_none()
        if rt is not None:
            await session.execute(update(RefreshToken).where(RefreshToken.family_id == rt.family_id,
                                                             RefreshToken.revoked_at.is_(None))
                                  .values(revoked_at=datetime.now(UTC)))


async def provision_external_user(session: AsyncSession, claims: dict) -> User:
    """First request from an identity-provider user (external_jwt mode): create user + personal org."""
    email = claims.get("email")
    if not email:
        raise AppError(401, "invalid_token", "Unauthenticated", "The identity token has no email.")
    user = User(email=email, display_name=(claims.get("name") or email.split("@")[0])[:120],
                external_subject=claims["sub"], email_verified_at=datetime.now(UTC))
    session.add(user)
    await session.flush()
    await create_personal_org(session, user, None)
    return user
