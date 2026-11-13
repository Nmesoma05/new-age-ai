"""OAuth 2.0 authorization-code flow with PKCE, and the token vault.

Flow
  1. start():    a workspace admin asks to connect. We create a random `state` (32 bytes) and PKCE verifier,
                 store sha256(state) + the encrypted verifier server-side for 10 minutes, and return the
                 provider's authorize URL. Nothing secret goes to the browser except the one-time state.
  2. complete(): the web app's /integrations/callback page posts {state, code} back WITH the user's session.
                 The state must exist, be unused, unexpired and belong to the same user. It's marked used before
                 anything else (single use, even if the exchange then fails). The code is exchanged with the
                 verifier; required scopes must all have been granted; tokens are encrypted and stored.
Tokens
  - Stored only encrypted (Fernet/MultiFernet) in integrations.encrypted_credentials; never returned by any API,
    never logged. Decrypted in memory only for a call.
  - Refreshed ahead of expiry (2-minute skew) under a row lock so concurrent requests don't refresh twice.
    `invalid_grant` -> status needs_reauth (user must reconnect); other failures keep the old token.
  - Re-encrypted under the newest key on next use after a key rotation.
  - Revocation: provider revoke endpoint (best effort), then the secret is destroyed locally and the row kept
    (status revoked) for the audit trail. If the provider call fails we say so and point to the account settings.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import (
    current_key_version,
    decrypt_bytes,
    decrypt_json,
    encrypt_bytes,
    encrypt_json,
)
from app.core.db import system_context, transaction
from app.integrations.http import (
    AuthExpired,
    CallContext,
    IntegrationError,
    ProviderLimits,
    json_of,
    request,
)
from app.models import Integration, OAuthState

STATE_TTL = timedelta(minutes=10)
REFRESH_SKEW = timedelta(minutes=2)


@dataclass(frozen=True)
class OAuthProvider:
    key: str
    authorize_url: str
    token_url: str
    revoke_url: str | None
    limits: ProviderLimits
    extra_authorize: dict = field(default_factory=dict)

    def client(self) -> tuple[str, str]:
        s = get_settings()
        if self.key == "google":
            if not s.google_oauth_client_id or not s.google_oauth_client_secret:
                raise IntegrationError("not_configured", "This integration isn't set up on this server yet.")
            return s.google_oauth_client_id, s.google_oauth_client_secret.get_secret_value()
        raise IntegrationError("not_configured", "This integration isn't set up on this server yet.")


GOOGLE = OAuthProvider(
    key="google", authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token", revoke_url="https://oauth2.googleapis.com/revoke",
    limits=ProviderLimits(hosts=frozenset({"oauth2.googleapis.com"}), rate_per_sec=5, burst=10),
    # offline = a refresh token; consent = Google re-issues it on reconnect
    extra_authorize={"access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"},
)


def redirect_uri() -> str:
    return get_settings().public_web_url.rstrip("/") + "/integrations/callback"


def _sha(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


async def start(session: AsyncSession, provider: OAuthProvider, integration_key: str, scopes: tuple[str, ...], *,
                user_id: uuid.UUID, org_id: uuid.UUID, workspace_id: uuid.UUID, return_to: str) -> str:
    client_id, _ = provider.client()
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    async with system_context(session):
        session.add(OAuthState(state_hash=_sha(state), provider=integration_key, user_id=user_id, org_id=org_id,
                               workspace_id=workspace_id, encrypted_verifier=encrypt_bytes(verifier.encode()),
                               scopes=list(scopes), return_to=return_to,
                               expires_at=datetime.now(UTC) + STATE_TTL))
        await session.flush()
    q = {"client_id": client_id, "redirect_uri": redirect_uri(), "response_type": "code", "scope": " ".join(scopes),
         "state": state, "code_challenge": _challenge(verifier), "code_challenge_method": "S256",
         **provider.extra_authorize}
    return f"{provider.authorize_url}?{urlencode(q)}"


@dataclass
class StateInfo:
    provider: str
    org_id: uuid.UUID
    workspace_id: uuid.UUID
    scopes: list[str]
    return_to: str


@dataclass
class Grant:
    state: StateInfo
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    granted: set[str]


async def _consume_state(user_id: uuid.UUID, state: str) -> dict:
    """Mark the state used in its OWN committed transaction, so it stays single-use even if what follows fails."""
    async with transaction(user_id, context="system") as s:
        row = (await s.execute(select(OAuthState).where(OAuthState.state_hash == _sha(state))
                               .with_for_update())).scalar_one_or_none()
        if row is None or row.user_id != user_id:
            return {"error": IntegrationError("bad_state", "This connection link isn't valid. Start again from Settings.")}
        if row.used_at is not None:
            return {"error": IntegrationError("state_used", "This connection link was already used. Start again.")}
        row.used_at = datetime.now(UTC)
        if row.expires_at < datetime.now(UTC):
            return {"error": IntegrationError("state_expired", "The connection took too long. Start again.")}
        return {"provider": row.provider, "org_id": row.org_id, "workspace_id": row.workspace_id,
                "scopes": list(row.scopes), "return_to": row.return_to,
                "verifier": decrypt_bytes(row.encrypted_verifier).decode()}


async def complete(session: AsyncSession, provider: OAuthProvider, *, user_id: uuid.UUID, state: str,
                   code: str) -> Grant:
    """Validate state (single-use, same user, unexpired) and exchange the code. Raises IntegrationError."""
    st = await _consume_state(user_id, state)
    if "error" in st:
        raise st["error"]
    row = StateInfo(**{k: v for k, v in st.items() if k != "verifier"})
    verifier = st["verifier"]
    client_id, client_secret = provider.client()
    ctx = CallContext(session, row.provider, "oauth.token_exchange", org_id=row.org_id, workspace_id=row.workspace_id)
    resp = await request(ctx, provider.limits, "POST", provider.token_url, idempotent=False, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(), "client_id": client_id,
        "client_secret": client_secret, "code_verifier": verifier})
    tok = json_of(resp)
    if "access_token" not in tok:
        raise IntegrationError("bad_response", "The provider didn't return an access token.")
    granted = set((tok.get("scope") or " ".join(row.scopes)).split())
    missing = [s for s in row.scopes if s not in granted]
    if missing:
        raise IntegrationError("scopes_missing", "Some permissions weren't granted, so this can't work. Connect "
                               "again and allow all requested access.")
    exp = datetime.now(UTC) + timedelta(seconds=int(tok["expires_in"])) if tok.get("expires_in") else None
    return Grant(row, tok["access_token"], tok.get("refresh_token"), exp, granted)


def seal(access_token: str, refresh_token: str | None) -> bytes:
    return encrypt_json({"access_token": access_token, "refresh_token": refresh_token})


async def mark(integration_id: uuid.UUID, *, status: str | None = None, last_error: str | None = None,
               failure: bool = False, synced: bool = False) -> None:
    """Record connection health in its own transaction (it must survive the request rolling back)."""
    async with transaction(None, context="system") as s:
        row = await s.get(Integration, integration_id, with_for_update={"key_share": True})
        if row is None:
            return
        now = datetime.now(UTC)
        if status:
            row.status = status
        if last_error is not None:
            row.last_error, row.last_error_at = last_error[:300], now
        if failure:
            row.consecutive_failures += 1
        if synced:
            row.last_sync_at, row.consecutive_failures, row.last_error = now, 0, None


async def access_token(integ: Integration, provider: OAuthProvider) -> str:
    """A valid access token for this connection, refreshing it if needed. Server-side only.

    Runs in its OWN transaction: a refreshed (possibly rotated) token must be saved even if the caller's request
    later fails, and health updates happen only after that transaction has released its row lock."""
    problem: tuple[str, IntegrationError] | None = None
    async with transaction(None, context="system") as s:
        row = (await s.execute(select(Integration).where(Integration.id == integ.id).with_for_update(key_share=True))).scalar_one()
        if row.status in ("revoked", "needs_reauth"):
            raise AuthExpired()
        creds = decrypt_json(row.encrypted_credentials)
        now = datetime.now(UTC)
        if row.token_expires_at and row.token_expires_at - REFRESH_SKEW > now:
            if row.key_version < current_key_version():  # re-encrypt under the newest key
                row.encrypted_credentials = seal(creds["access_token"], creds.get("refresh_token"))
                row.key_version = current_key_version()
            row.last_used_at = now
            return creds["access_token"]
        if not creds.get("refresh_token"):
            problem = ("reauth", AuthExpired())
        else:
            client_id, client_secret = provider.client()
            ctx = CallContext(s, row.provider, "oauth.refresh", org_id=row.org_id, workspace_id=row.workspace_id,
                              integration_id=row.id)
            try:
                # Safe to retry: a refresh changes nothing the user can see.
                resp = await request(ctx, provider.limits, "POST", provider.token_url, idempotent=True, data={
                    "grant_type": "refresh_token", "refresh_token": creds["refresh_token"], "client_id": client_id,
                    "client_secret": client_secret})
                tok = json_of(resp)
                row.encrypted_credentials = seal(tok["access_token"], tok.get("refresh_token") or creds["refresh_token"])
                row.key_version = current_key_version()
                row.token_expires_at = now + timedelta(seconds=int(tok.get("expires_in", 3600)))
                row.last_refreshed_at = row.last_used_at = now
                return tok["access_token"]
            except IntegrationError as e:
                # invalid_grant (400/401): revoked by the user, expired, or the password changed
                problem = ("reauth", AuthExpired()) if e.status in (400, 401) else ("fail", e)
    kind, err = problem
    if kind == "reauth":
        await mark(integ.id, status="needs_reauth", last_error="Access was revoked or has expired: reconnect.")
    raise err  # other failures: the caller records them once (see api/v1/integrations.py sync)


async def revoke(session: AsyncSession, integ: Integration, provider: OAuthProvider | None) -> bool:
    """Revoke at the provider (best effort) and destroy our copy. Returns whether the provider confirmed."""
    confirmed = False
    async with system_context(session):
        row = (await session.execute(select(Integration).where(Integration.id == integ.id)
                                     .with_for_update(key_share=True))).scalar_one()
        if provider and provider.revoke_url and row.status != "revoked" and row.encrypted_credentials != b"\x00":
            creds = decrypt_json(row.encrypted_credentials)
            token = creds.get("refresh_token") or creds.get("access_token")
            try:
                ctx = CallContext(session, row.provider, "oauth.revoke", org_id=row.org_id,
                                  workspace_id=row.workspace_id, integration_id=row.id)
                await request(ctx, provider.limits, "POST", provider.revoke_url, idempotent=True, data={"token": token})
                confirmed = True
            except IntegrationError:
                confirmed = False
        await session.execute(update(Integration).where(Integration.id == row.id).values(
            status="revoked", encrypted_credentials=b"\x00", token_expires_at=None))
        await session.flush()
    return confirmed
