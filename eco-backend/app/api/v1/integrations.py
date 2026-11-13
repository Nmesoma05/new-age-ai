"""External integrations: catalog, per-workspace connections (OAuth), sync, and the app-wide public data services.

Rules enforced here:
- Only integrations marked `implemented` in the catalog can be connected or used. Planned ones are listed honestly.
- Connecting or disconnecting an account needs an organisation owner/admin. Syncing (read-only) needs workspace write.
- Tokens never leave the server: responses carry metadata only.
- Every provider failure is reported as what it is; nothing is shown as synced, imported or converted unless it was.
"""
from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.db import system_context
from app.core.deps import Principal, WsCtx, get_principal, ws_ctx
from app.core.errors import AppError, forbidden, not_found
from app.core.permissions import org_can
from app.integrations import catalog, oauth, providers
from app.integrations.http import CallContext, IntegrationError
from app.integrations.http import request as provider_request
from app.models import Integration, Opportunity
from app.services import audit

router = APIRouter(tags=["integrations"])

STATUS_FOR = {"not_configured": 503, "outbound_disabled": 503, "needs_reauth": 409, "rate_limited": 429,
              "provider_unavailable": 503, "network_error": 502, "provider_error": 502, "outcome_unknown": 502,
              "bad_response": 502, "response_too_large": 502, "permission_denied": 403, "host_not_allowed": 500,
              "bad_state": 400, "state_used": 400, "state_expired": 400, "scopes_missing": 400,
              "no_channel": 400, "account_changed": 409, "bad_currency": 422, "unsupported_currency": 422,
              "bad_request": 502, "access_denied": 400}


def _err(e: IntegrationError) -> AppError:
    return AppError(STATUS_FOR.get(e.code, 502), e.code, e.message, extra={"retryable": e.retryable})


def _implemented(key: str) -> catalog.Integration:
    item = catalog.BY_KEY.get(key)
    if item is None:
        raise not_found("integration")
    if item.status != "implemented":
        raise AppError(409, "integration_planned", f"{item.name} isn't available yet. It's on the roadmap; see the "
                       "integrations page for what it needs.")
    return item


OAUTH_FOR = {"youtube": (oauth.GOOGLE, providers.YT_SCOPES)}


def _configured(item: catalog.Integration) -> bool:
    s = get_settings()
    if item.key == "youtube":
        return bool(s.google_oauth_client_id and s.google_oauth_client_secret) and s.outbound_http_enabled
    if item.key == "remotive":
        return s.remotive_enabled and s.outbound_http_enabled
    if item.key == "fx_exchangerate_api":
        return s.fx_provider_enabled and s.outbound_http_enabled
    return False


async def _org_admin(session, user_org: uuid.UUID) -> None:
    role = (await session.execute(text("SELECT app.org_role(:o)"), {"o": user_org})).scalar_one()
    if not org_can(role, "org.integrations.manage"):
        raise forbidden("Only an organisation owner or admin can connect or disconnect accounts.")


def _out(i: Integration) -> dict:
    item = catalog.BY_KEY.get(i.provider)
    return {"id": str(i.id), "provider": i.provider, "name": item.name if item else i.provider, "status": i.status,
            "account_label": i.account_label, "external_account_id": i.external_account_id, "scopes": i.scopes,
            "access": item.access if item else None, "last_sync_at": i.last_sync_at, "last_error": i.last_error,
            "last_error_at": i.last_error_at, "consecutive_failures": i.consecutive_failures,
            "connected_at": i.created_at}


# ================================================================== catalog
@router.get("/v1/integrations/catalog")
async def get_catalog(product: str | None = Query(None, pattern="^(creator|business|freelancer)$"),
                      p: Principal = Depends(get_principal)):
    items = catalog.for_product(product) if product else [i.as_dict() for i in catalog.CATALOG]
    for it in items:
        it["configured"] = _configured(catalog.BY_KEY[it["key"]])
    return {"verified_on": catalog.VERIFIED_ON,
            "implemented": [i for i in items if i["status"] == "implemented"],
            "planned": [i for i in items if i["status"] == "planned"]}


# ================================================================== workspace connections
async def _ws_integrations(ctx: WsCtx, include_revoked: bool = False) -> list[Integration]:
    # integrations RLS is org-admin only; workspace members may see connection health (never secrets)
    async with system_context(ctx.session):
        q = select(Integration).where(Integration.workspace_id == ctx.workspace.id,
                                      Integration.org_id == ctx.workspace.org_id)
        if not include_revoked:
            q = q.where(Integration.status != "revoked")
        return list((await ctx.session.execute(q.order_by(Integration.created_at))).scalars().all())


@router.get("/v1/workspaces/{workspace_id}/integrations")
async def list_connections(ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.read")
    rows = await _ws_integrations(ctx)
    return {"connections": [_out(i) for i in rows],
            "available": [{**i, "configured": _configured(catalog.BY_KEY[i["key"]])}
                          for i in catalog.for_product(ctx.workspace.product) if i["connectable"]]}


class ConnectIn(BaseModel):
    return_to: str = Field("/", max_length=300)


@router.post("/v1/workspaces/{workspace_id}/integrations/{key}/connect")
async def connect(key: str, body: ConnectIn, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.read")
    await _org_admin(ctx.session, ctx.workspace.org_id)
    item = _implemented(key)
    if not item.connectable or key not in OAUTH_FOR:
        raise AppError(400, "not_connectable", f"{item.name} is a shared service; there's no account to connect.")
    if ctx.workspace.product not in item.products:
        raise AppError(400, "wrong_product", f"{item.name} isn't used in this kind of workspace.")
    if not re.fullmatch(r"/(?!/)[A-Za-z0-9/_\-?=&.%]*", body.return_to):
        raise AppError(422, "bad_return_to", "return_to must be a path on this site.")
    provider, scopes = OAUTH_FOR[key]
    try:
        url = await oauth.start(ctx.session, provider, key, scopes, user_id=ctx.principal.id,
                                org_id=ctx.workspace.org_id, workspace_id=ctx.workspace.id, return_to=body.return_to)
    except IntegrationError as e:
        raise _err(e) from e
    return {"authorization_url": url, "scopes": list(scopes),
            "note": "You'll be asked to allow read-only access. Nothing is posted or changed on your account."}


class CompleteIn(BaseModel):
    state: str = Field(min_length=10, max_length=200)
    code: str | None = Field(None, max_length=2000)
    error: str | None = Field(None, max_length=200)


@router.post("/v1/integrations/oauth/complete")
async def complete(body: CompleteIn, request: Request, p: Principal = Depends(get_principal)):
    s = p.session
    if body.error or not body.code:
        # the user declined (or the provider refused). Burn the state and say so; nothing was connected.
        await oauth._consume_state(p.id, body.state)
        raise AppError(400, "access_denied", "Access wasn't granted, so nothing was connected.")
    # which provider? the state row knows; peek without consuming
    key = await _state_provider(body.state)
    if key not in OAUTH_FOR:
        await oauth._consume_state(p.id, body.state)
        raise AppError(400, "bad_state", "This connection link isn't valid. Start again from Settings.")
    provider, _ = OAUTH_FOR[key]
    try:
        grant = await oauth.complete(s, provider, user_id=p.id, state=body.state, code=body.code)
    except IntegrationError as e:
        raise _err(e) from e
    st = grant.state
    await _org_admin(s, st.org_id)  # role may have changed while the user was at the provider
    try:
        ident = await providers.youtube_identity(s, grant.access_token, st.org_id, st.workspace_id)
    except IntegrationError as e:
        await _discard_grant(s, provider, grant, st)
        raise _err(e) from e
    now = datetime.now(UTC)
    async with system_context(s):
        row = (await s.execute(select(Integration).where(
            Integration.workspace_id == st.workspace_id, Integration.provider == key,
            Integration.external_account_id == ident["id"], Integration.status != "revoked"))).scalar_one_or_none()
        sealed = oauth.seal(grant.access_token, grant.refresh_token)
        if row is None:
            row = Integration(org_id=st.org_id, workspace_id=st.workspace_id, provider=key,
                              external_account_id=ident["id"], created_by=p.id, encrypted_credentials=sealed)
            s.add(row)
        elif not grant.refresh_token:
            # Google normally re-issues one with prompt=consent; keep the old one if not
            old = oauth.decrypt_json(row.encrypted_credentials)
            sealed = oauth.seal(grant.access_token, old.get("refresh_token"))
        row.encrypted_credentials = sealed
        row.status, row.auth_type, row.account_label = "connected", "oauth2", ident["title"][:200]
        row.scopes, row.token_expires_at = sorted(grant.granted), grant.expires_at
        row.key_version, row.last_refreshed_at = oauth.current_key_version(), now
        row.last_error, row.consecutive_failures = None, 0
        await s.flush()
        await audit.record(s, "integration.connected", actor_id=p.id, org_id=st.org_id, workspace_id=st.workspace_id,
                           target_type="integration", target_id=row.id,
                           metadata={"provider": key, "scopes": sorted(grant.granted), "account": ident["title"]},
                           request=request)
        out = _out(row)
    return {"connection": out, "return_to": st.return_to}


async def _state_provider(state: str) -> str | None:
    from app.core.db import transaction
    from app.models import OAuthState
    async with transaction(None, context="system") as t:
        return (await t.execute(select(OAuthState.provider).where(
            OAuthState.state_hash == oauth._sha(state)))).scalar_one_or_none()


async def _discard_grant(s, provider: oauth.OAuthProvider, grant: oauth.Grant, st: oauth.StateInfo) -> None:
    """We won't keep a token we can't use: ask the provider to revoke it (best effort)."""
    if not provider.revoke_url:
        return
    try:
        await provider_request(CallContext(s, st.provider, "oauth.revoke_unused", org_id=st.org_id,
                                           workspace_id=st.workspace_id), provider.limits, "POST",
                               provider.revoke_url, idempotent=True,
                               data={"token": grant.refresh_token or grant.access_token})
    except IntegrationError:
        pass


async def _own(ctx: WsCtx, integration_id: uuid.UUID) -> Integration:
    for i in await _ws_integrations(ctx, include_revoked=True):
        if i.id == integration_id:
            return i
    raise not_found("integration")


@router.delete("/v1/workspaces/{workspace_id}/integrations/{integration_id}")
async def disconnect(integration_id: uuid.UUID, request: Request, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.read")
    await _org_admin(ctx.session, ctx.workspace.org_id)
    integ = await _own(ctx, integration_id)
    if integ.status == "revoked":
        return {"status": "revoked", "provider_confirmed": None, "message": "Already disconnected."}
    provider = OAUTH_FOR.get(integ.provider, (None, ()))[0]
    confirmed = await oauth.revoke(ctx.session, integ, provider)
    async with system_context(ctx.session):
        await audit.record(ctx.session, "integration.revoked", actor_id=ctx.principal.id, org_id=integ.org_id,
                           workspace_id=integ.workspace_id, target_type="integration", target_id=integ.id,
                           metadata={"provider": integ.provider, "provider_confirmed": confirmed}, request=request)
    msg = ("Disconnected. The provider confirmed access was removed." if confirmed else
           "Disconnected here and our copy of the access was deleted, but the provider didn't confirm removal. "
           "To be sure, remove this app at https://myaccount.google.com/permissions.")
    return {"status": "revoked", "provider_confirmed": confirmed, "message": msg}


class SyncIn(BaseModel):
    start: date | None = None
    end: date | None = None


@router.post("/v1/workspaces/{workspace_id}/integrations/{integration_id}/sync")
async def sync(integration_id: uuid.UUID, body: SyncIn, request: Request, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.write")
    integ = await _own(ctx, integration_id)
    if integ.status == "revoked":
        raise AppError(409, "revoked", "This connection was removed. Connect the account again.")
    if integ.status == "needs_reauth":
        raise AppError(409, "needs_reauth", "This connection needs renewing. Reconnect the account.")
    _implemented(integ.provider)
    end = body.end or (datetime.now(UTC).date() - timedelta(days=1))
    start = body.start or (end - timedelta(days=27))
    if start > end or (end - start).days > 365:
        raise AppError(422, "bad_range", "Pick a range of up to a year, start before end.")
    try:
        result = await providers.youtube_sync(ctx.session, integ, ctx.principal.id, start, end)
    except IntegrationError as e:
        if e.code != "needs_reauth":  # access_token already recorded reauth
            await oauth.mark(integ.id, last_error=e.message, failure=True)
        raise _err(e) from e
    await audit.record(ctx.session, "integration.synced", actor_id=ctx.principal.id, org_id=integ.org_id,
                       workspace_id=integ.workspace_id, target_type="integration", target_id=integ.id,
                       metadata={"provider": integ.provider, "videos": result["videos"]}, request=request)
    return {**result, "source": "YouTube Analytics API",
            "note": "YouTube Analytics usually lags 2–3 days; the most recent days may be incomplete."}


# ================================================================== exchange rates (app-wide, no account)
@router.get("/v1/fx/convert")
async def fx_convert(amount: Decimal = Query(gt=0, le=Decimal("1e12")), from_: str = Query(alias="from"),
                     to: str = Query(), p: Principal = Depends(get_principal)):
    try:
        return await providers.convert(p.session, amount, from_, to)
    except IntegrationError as e:
        raise _err(e) from e


# ================================================================== Remotive (freelancer, app-wide feed)
@router.get("/v1/workspaces/{workspace_id}/jobs/remotive")
async def remotive_search(q: str = Query("", max_length=100), category: str = Query("", max_length=60),
                          ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.read")
    if ctx.workspace.product != "freelancer":
        raise not_found("workspace")
    try:
        feed = await providers.remotive_feed(ctx.session)
    except IntegrationError as e:
        raise _err(e) from e
    return {"jobs": providers.search_jobs(feed, q, category), "fetched_at": feed["fetched_at"],
            "stale": feed["stale"], "attribution": feed["attribution"]}


class ImportIn(BaseModel):
    job_id: str = Field(min_length=1, max_length=40)


KIND_FOR = {"freelance": "freelance_project", "contract": "contract", "internship": "internship"}


@router.post("/v1/workspaces/{workspace_id}/jobs/remotive/import", status_code=201)
async def remotive_import(body: ImportIn, request: Request, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.write")
    if ctx.workspace.product != "freelancer":
        raise not_found("workspace")
    try:
        feed = await providers.remotive_feed(ctx.session)
    except IntegrationError as e:
        raise _err(e) from e
    job = next((j for j in feed["jobs"] if j["id"] == body.job_id), None)
    if job is None:
        raise AppError(404, "job_gone", "That listing isn't in the current Remotive feed. It may have closed.")
    s = ctx.session
    dup = (await s.execute(select(Opportunity.id).where(Opportunity.workspace_id == ctx.workspace.id,
                                                        Opportunity.url == job["url"]))).scalar_one_or_none()
    if dup:
        raise AppError(409, "already_saved", "You've already saved this listing.", extra={"id": str(dup)})
    remote_type, tokens = providers.location_to_codes(job["location"])
    desc = (f"Salary as listed: {job['salary']}\n\n" if job["salary"] else "") + job["description"]
    opp = Opportunity(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id,
                      kind=KIND_FOR.get(job["job_type"], "job"), title=job["title"][:200] or "Untitled",
                      organisation=job["company"][:200], url=job["url"], source="integration", source_name="Remotive",
                      remote_type=remote_type, eligible_countries=tokens,
                      location_note=f"Listed location: {job['location']}"[:300] if job["location"] else "",
                      description=desc[:20000], status="unverified", created_by=ctx.principal.id,
                      verification_note="Imported from Remotive's public feed (listings are delayed 24h). Open the "
                                        "Remotive page to confirm it's still open before applying.")
    s.add(opp)
    await s.flush()
    await audit.record(s, "opportunity.imported", actor_id=ctx.principal.id, org_id=ctx.workspace.org_id,
                       workspace_id=ctx.workspace.id, target_type="opportunity", target_id=opp.id,
                       metadata={"source": "remotive", "job_id": job["id"]}, request=request)
    return {"id": str(opp.id), "status": "unverified", "url": job["url"], "attribution": feed["attribution"]}
