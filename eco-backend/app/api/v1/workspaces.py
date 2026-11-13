import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select

from app.core.deps import OrgCtx, WsCtx, org_ctx, ws_ctx
from app.core.errors import AppError, forbidden, not_found
from app.core.pagination import page_of, paginate
from app.models import OrgMember, ProductAccess, Project, Workspace, WorkspaceMember
from app.schemas.common import (
    ProjectIn,
    ProjectOut,
    ProjectPatch,
    WorkspaceIn,
    WorkspaceOut,
    WorkspacePatch,
    WorkspaceWithRole,
    WsMemberIn,
    WsMemberOut,
    WsMemberPatch,
)
from app.services import audit, billing

router = APIRouter(prefix="/v1", tags=["workspaces"])


@router.get("/orgs/{org_id}/workspaces", response_model=list[WorkspaceWithRole])
async def list_workspaces(product: str | None = Query(default=None, pattern="^(creator|business|freelancer)$"),
                          ctx: OrgCtx = Depends(org_ctx)):
    s = ctx.principal.session
    stmt = (select(Workspace, func.app.ws_role(Workspace.id))
            .where(Workspace.org_id == ctx.org.id, Workspace.deleted_at.is_(None)).order_by(Workspace.created_at, Workspace.id))
    if product:
        stmt = stmt.where(Workspace.product == product)
    rows = (await s.execute(stmt)).all()
    ent = await billing.entitlements(s, ctx.org.id)
    out = []
    for w, role in rows:
        if role in (None, "client_approver"):
            continue
        out.append(WorkspaceWithRole(**WorkspaceOut.model_validate(w).model_dump(), role=role,
                                     read_only=await billing.workspace_is_read_only(s, w, ent)))
    return out


@router.post("/orgs/{org_id}/workspaces", response_model=WorkspaceOut, status_code=201)
async def create_workspace(body: WorkspaceIn, request: Request, ctx: OrgCtx = Depends(org_ctx)):
    ctx.require("org.workspaces.create")
    return await create_workspace_row(ctx.principal, ctx.org, body.name, body.product, request)


async def create_workspace_row(principal, org, name: str, product: str, request: Request | None) -> Workspace:
    """Shared by the workspaces API, Creator onboarding and 'new client': product access, the freelancer rule and
    the plan's workspace limit are always enforced here. The caller must already have checked the org role."""
    s = principal.session
    pa = await s.get(ProductAccess, (org.id, product))
    if pa is None or pa.status != "active":
        raise forbidden(f"Turn on the {product} product for this organisation first.", code="product_not_enabled")
    if product == "freelancer" and org.kind != "personal":
        raise forbidden("Freelancer profiles live in your personal organisation so teams can't see them.",
                        code="personal_org_required")
    ent = await billing.entitlements(s, org.id)
    count = (await s.execute(select(func.count()).select_from(Workspace).where(
        Workspace.org_id == org.id, Workspace.deleted_at.is_(None)))).scalar_one()
    if count >= ent.plan.max_workspaces:
        raise AppError(402, "workspace_limit_reached", "Workspace limit reached",
                       f"Your {ent.plan.name} plan includes {ent.plan.max_workspaces} workspace(s).")
    ws = Workspace(org_id=org.id, product=product, name=name, created_by=principal.id)
    s.add(ws)
    await s.flush()
    await s.refresh(ws)
    await audit.record(s, "workspace.created", actor_id=principal.id, org_id=org.id, workspace_id=ws.id,
                       target_type="workspace", target_id=ws.id, metadata={"product": product}, request=request)
    return ws


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceWithRole)
async def get_workspace(ctx: WsCtx = Depends(ws_ctx)):
    ent = await billing.entitlements(ctx.session, ctx.workspace.org_id)
    return WorkspaceWithRole(**WorkspaceOut.model_validate(ctx.workspace).model_dump(), role=ctx.role,
                             read_only=await billing.workspace_is_read_only(ctx.session, ctx.workspace, ent))


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceOut)
async def rename_workspace(body: WorkspacePatch, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.manage")
    ctx.workspace.name = body.name
    await ctx.session.flush()
    await audit.record(ctx.session, "workspace.renamed", actor_id=ctx.principal.id, org_id=ctx.workspace.org_id,
                       workspace_id=ctx.workspace.id, target_type="workspace", target_id=ctx.workspace.id,
                       request=ctx.request)
    return ctx.workspace


@router.delete("/workspaces/{workspace_id}", status_code=204)
async def delete_workspace(ctx: WsCtx = Depends(ws_ctx)):
    role = (await ctx.session.execute(select(OrgMember.role).where(
        OrgMember.org_id == ctx.workspace.org_id, OrgMember.user_id == ctx.principal.id))).scalar_one_or_none()
    if role != "owner":
        raise forbidden("Only the organisation owner can delete a workspace.")
    ctx.workspace.deleted_at = datetime.now(UTC)  # soft delete; purge job removes it after 30 days
    await ctx.session.flush()
    await audit.record(ctx.session, "workspace.deleted", actor_id=ctx.principal.id, org_id=ctx.workspace.org_id,
                       workspace_id=ctx.workspace.id, target_type="workspace", target_id=ctx.workspace.id,
                       request=ctx.request)
    return Response(status_code=204)


# ---------------------------------------------------------------- workspace members
@router.get("/workspaces/{workspace_id}/members", response_model=list[WsMemberOut])
async def list_ws_members(ctx: WsCtx = Depends(ws_ctx)):
    rows = (await ctx.session.execute(select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == ctx.workspace.id).order_by(WorkspaceMember.created_at))).scalars().all()
    return [WsMemberOut(user_id=m.user_id, role=m.role) for m in rows]


@router.post("/workspaces/{workspace_id}/members", response_model=WsMemberOut, status_code=201)
async def add_ws_member(body: WsMemberIn, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.manage")
    if ctx.workspace.product == "freelancer":
        raise forbidden("Freelancer profiles are private to their owner.", code="private_workspace")
    if await ctx.session.get(OrgMember, (ctx.workspace.org_id, body.user_id)) is None:
        raise AppError(422, "not_org_member", "Not an organisation member", "Add them to the organisation first.")
    if await ctx.session.get(WorkspaceMember, (ctx.workspace.id, body.user_id)):
        raise AppError(409, "already_member", "Already a workspace member")
    ctx.session.add(WorkspaceMember(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, user_id=body.user_id,
                                    role=body.role))
    await ctx.session.flush()
    await audit.record(ctx.session, "workspace.member_added", actor_id=ctx.principal.id, org_id=ctx.workspace.org_id,
                       workspace_id=ctx.workspace.id, target_type="user", target_id=body.user_id,
                       metadata={"role": body.role}, request=ctx.request)
    return WsMemberOut(user_id=body.user_id, role=body.role)


@router.patch("/workspaces/{workspace_id}/members/{user_id}", response_model=WsMemberOut)
async def update_ws_member(user_id: uuid.UUID, body: WsMemberPatch, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.manage")
    m = await ctx.session.get(WorkspaceMember, (ctx.workspace.id, user_id))
    if m is None:
        raise not_found("member")
    before, m.role = m.role, body.role
    await ctx.session.flush()
    await audit.record(ctx.session, "workspace.member_role_changed", actor_id=ctx.principal.id,
                       org_id=ctx.workspace.org_id, workspace_id=ctx.workspace.id, target_type="user",
                       target_id=user_id, metadata={"from": before, "to": body.role}, request=ctx.request)
    return WsMemberOut(user_id=user_id, role=m.role)


@router.delete("/workspaces/{workspace_id}/members/{user_id}", status_code=204)
async def remove_ws_member(user_id: uuid.UUID, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.manage")
    m = await ctx.session.get(WorkspaceMember, (ctx.workspace.id, user_id))
    if m is None:
        raise not_found("member")
    await ctx.session.delete(m)
    await ctx.session.flush()
    await audit.record(ctx.session, "workspace.member_removed", actor_id=ctx.principal.id, org_id=ctx.workspace.org_id,
                       workspace_id=ctx.workspace.id, target_type="user", target_id=user_id, request=ctx.request)
    return Response(status_code=204)


# ---------------------------------------------------------------- projects
@router.get("/workspaces/{workspace_id}/projects")
async def list_projects(cursor: str | None = None, limit: int = 25, ctx: WsCtx = Depends(ws_ctx)):
    stmt = paginate(select(Project).where(Project.workspace_id == ctx.workspace.id), Project, cursor, limit)
    rows = (await ctx.session.execute(stmt)).scalars().all()
    return page_of(list(rows), limit, lambda r: ProjectOut.model_validate(r))


@router.post("/workspaces/{workspace_id}/projects", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectIn, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.write")
    pr = Project(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, name=body.name,
                 description=body.description, created_by=ctx.principal.id)
    ctx.session.add(pr)
    await ctx.session.flush()
    await ctx.session.refresh(pr)
    return pr


@router.patch("/workspaces/{workspace_id}/projects/{project_id}", response_model=ProjectOut)
async def update_project(project_id: uuid.UUID, body: ProjectPatch, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.write")
    pr = await ctx.session.get(Project, project_id)
    if pr is None or pr.workspace_id != ctx.workspace.id:
        raise not_found("project")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(pr, k, v)
    await ctx.session.flush()
    await ctx.session.refresh(pr)
    return pr
