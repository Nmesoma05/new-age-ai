"""Integrations (encrypted credentials) and the organisation audit log."""
import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select

from app.core.crypto import encrypt_json
from app.core.deps import OrgCtx, org_ctx
from app.core.errors import AppError, not_found
from app.models import AuditEvent, Integration, Workspace
from app.schemas.common import AuditOut, IntegrationIn, IntegrationOut
from app.services import audit

router = APIRouter(prefix="/v1/orgs/{org_id}", tags=["integrations", "audit"])


@router.get("/integrations", response_model=list[IntegrationOut])
async def list_integrations(ctx: OrgCtx = Depends(org_ctx)):
    ctx.require("org.integrations.manage")
    return (await ctx.principal.session.execute(select(Integration).where(
        Integration.org_id == ctx.org.id, Integration.status != "revoked").order_by(Integration.created_at))).scalars().all()


@router.post("/integrations", response_model=IntegrationOut, status_code=201)
async def connect_integration(body: IntegrationIn, request: Request, ctx: OrgCtx = Depends(org_ctx)):
    """Stores a connection record. No provider API is called here: each integration needs a verified
    connector (architecture §12) before anything uses these credentials."""
    ctx.require("org.integrations.manage")
    s = ctx.principal.session
    if body.workspace_id:
        ws = await s.get(Workspace, body.workspace_id)
        if ws is None or ws.org_id != ctx.org.id:
            raise not_found("workspace")
    if not body.credentials:
        raise AppError(422, "credentials_required", "Credentials required")
    from app.integrations.catalog import BY_KEY
    if body.provider in BY_KEY:
        # catalog providers connect only through their verified flow (OAuth + scope checks), never pasted secrets
        raise AppError(400, "use_connect_flow", "Connect this account from the workspace's Integrations settings.")
    integ = Integration(org_id=ctx.org.id, workspace_id=body.workspace_id, provider=body.provider,
                        account_label=body.account_label, scopes=body.scopes,
                        encrypted_credentials=encrypt_json(body.credentials), created_by=ctx.principal.id)
    s.add(integ)
    await s.flush()
    await s.refresh(integ)
    await audit.record(s, "integration.connected", actor_id=ctx.principal.id, org_id=ctx.org.id,
                       workspace_id=body.workspace_id, target_type="integration", target_id=integ.id,
                       metadata={"provider": body.provider, "scopes": body.scopes}, request=request)
    return integ


@router.delete("/integrations/{integration_id}", status_code=204)
async def revoke_integration(integration_id: uuid.UUID, request: Request, ctx: OrgCtx = Depends(org_ctx)):
    ctx.require("org.integrations.manage")
    s = ctx.principal.session
    integ = await s.get(Integration, integration_id)
    if integ is None or integ.org_id != ctx.org.id:
        raise not_found("integration")
    integ.status = "revoked"
    integ.encrypted_credentials = b"\x00"  # destroy the secret; keep the row for the audit trail
    await s.flush()
    await audit.record(s, "integration.revoked", actor_id=ctx.principal.id, org_id=ctx.org.id,
                       target_type="integration", target_id=integ.id, metadata={"provider": integ.provider},
                       request=request)
    return Response(status_code=204)


@router.get("/audit-events")
async def list_audit(before_id: int | None = None, limit: int = Query(default=50, ge=1, le=200),
                     ctx: OrgCtx = Depends(org_ctx)):
    ctx.require("org.audit.read")
    stmt = select(AuditEvent).where(AuditEvent.org_id == ctx.org.id)
    if before_id:
        stmt = stmt.where(AuditEvent.id < before_id)
    rows = (await ctx.principal.session.execute(stmt.order_by(AuditEvent.id.desc()).limit(limit + 1))).scalars().all()
    more = len(rows) > limit
    rows = rows[:limit]
    return {"data": [AuditOut(id=r.id, action=r.action, actor_user_id=r.actor_user_id, workspace_id=r.workspace_id,
                              target_type=r.target_type, target_id=r.target_id, metadata=r.metadata_,
                              created_at=r.created_at) for r in rows],
            "next_cursor": str(rows[-1].id) if more and rows else None}
