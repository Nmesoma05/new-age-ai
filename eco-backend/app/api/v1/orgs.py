import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select

from app.core.db import system_context
from app.core.deps import OrgCtx, Principal, get_principal, org_ctx
from app.core.errors import AppError, forbidden, not_found
from app.models import Organisation, OrgMember, ProductAccess, Team, TeamMember, User
from app.schemas.common import (
    MemberIn,
    MemberOut,
    MemberPatch,
    OrgIn,
    OrgOut,
    OrgWithRole,
    ProductIn,
    ProductOut,
    TeamIn,
    TeamMemberIn,
    TeamOut,
)
from app.services import audit, billing

router = APIRouter(prefix="/v1", tags=["organisations"])


@router.get("/orgs", response_model=list[OrgWithRole])
async def list_orgs(p: Principal = Depends(get_principal)):
    rows = (await p.session.execute(
        select(Organisation, OrgMember.role).join(OrgMember, OrgMember.org_id == Organisation.id)
        .where(OrgMember.user_id == p.id, Organisation.deleted_at.is_(None)).order_by(Organisation.created_at)
    )).all()
    return [OrgWithRole(**OrgOut.model_validate(o).model_dump(), role=r) for o, r in rows]


@router.post("/orgs", response_model=OrgOut, status_code=201)
async def create_org(body: OrgIn, request: Request, p: Principal = Depends(get_principal)):
    org = Organisation(name=body.name, kind="team", owner_user_id=p.id)
    p.session.add(org)
    await p.session.flush()
    p.session.add(OrgMember(org_id=org.id, user_id=p.id, role="owner"))
    await p.session.flush()
    await p.session.refresh(org)
    await audit.record(p.session, "org.created", actor_id=p.id, org_id=org.id, target_type="org", target_id=org.id,
                       request=request)
    return org


@router.get("/orgs/{org_id}", response_model=OrgWithRole)
async def get_org(ctx: OrgCtx = Depends(org_ctx)):
    return OrgWithRole(**OrgOut.model_validate(ctx.org).model_dump(), role=ctx.role)


@router.patch("/orgs/{org_id}", response_model=OrgOut)
async def update_org(body: OrgIn, request: Request, ctx: OrgCtx = Depends(org_ctx)):
    ctx.require("org.update")
    ctx.org.name = body.name
    await ctx.principal.session.flush()
    await audit.record(ctx.principal.session, "org.updated", actor_id=ctx.principal.id, org_id=ctx.org.id,
                       target_type="org", target_id=ctx.org.id, request=request)
    return ctx.org


# ---------------------------------------------------------------- members
@router.get("/orgs/{org_id}/members", response_model=list[MemberOut])
async def list_members(ctx: OrgCtx = Depends(org_ctx)):
    rows = (await ctx.principal.session.execute(
        select(OrgMember, User).join(User, User.id == OrgMember.user_id).where(OrgMember.org_id == ctx.org.id)
        .order_by(OrgMember.created_at))).all()
    return [MemberOut(user_id=u.id, display_name=u.display_name, email=u.email, role=m.role) for m, u in rows]


@router.post("/orgs/{org_id}/members", response_model=MemberOut, status_code=201)
async def add_member(body: MemberIn, request: Request, ctx: OrgCtx = Depends(org_ctx)):
    ctx.require("org.members.manage")
    s = ctx.principal.session
    if ctx.org.kind == "personal":
        raise forbidden("Personal organisations can't have other members. Create a team organisation.",
                        code="personal_org")
    ent = await billing.entitlements(s, ctx.org.id)
    seats = (await s.execute(select(func.count()).select_from(OrgMember).where(OrgMember.org_id == ctx.org.id))).scalar_one()
    if seats >= ent.plan.max_seats:
        raise AppError(402, "seat_limit_reached", "Seat limit reached",
                       f"Your {ent.plan.name} plan includes {ent.plan.max_seats} seat(s).")
    async with system_context(s, ctx.principal.id):
        user = (await s.execute(select(User).where(User.email == str(body.email).lower(),
                                                   User.deleted_at.is_(None)))).scalar_one_or_none()
    if user is None:
        raise AppError(404, "user_not_found", "No account with that email",
                       "Ask them to sign up first, then add them.")
    if await s.get(OrgMember, (ctx.org.id, user.id)):
        raise AppError(409, "already_member", "Already a member")
    s.add(OrgMember(org_id=ctx.org.id, user_id=user.id, role=body.role))
    await s.flush()
    await audit.record(s, "org.member_added", actor_id=ctx.principal.id, org_id=ctx.org.id, target_type="user",
                       target_id=user.id, metadata={"role": body.role}, request=request)
    return MemberOut(user_id=user.id, display_name=user.display_name, email=user.email, role=body.role)


async def _member(ctx: OrgCtx, user_id: uuid.UUID) -> OrgMember:
    m = await ctx.principal.session.get(OrgMember, (ctx.org.id, user_id))
    if m is None:
        raise not_found("member")
    if m.role == "owner":
        raise forbidden("The owner's role can't be changed or removed. Transfer ownership first.", code="owner_protected")
    return m


@router.patch("/orgs/{org_id}/members/{user_id}", response_model=MemberOut)
async def update_member(user_id: uuid.UUID, body: MemberPatch, request: Request, ctx: OrgCtx = Depends(org_ctx)):
    ctx.require("org.members.manage")
    m = await _member(ctx, user_id)
    before, m.role = m.role, body.role
    await ctx.principal.session.flush()
    u = await ctx.principal.session.get(User, user_id)
    await audit.record(ctx.principal.session, "org.member_role_changed", actor_id=ctx.principal.id, org_id=ctx.org.id,
                       target_type="user", target_id=user_id, metadata={"from": before, "to": body.role},
                       request=request)
    return MemberOut(user_id=user_id, display_name=u.display_name, email=u.email, role=m.role)


@router.delete("/orgs/{org_id}/members/{user_id}", status_code=204)
async def remove_member(user_id: uuid.UUID, request: Request, ctx: OrgCtx = Depends(org_ctx)):
    ctx.require("org.members.manage")
    m = await _member(ctx, user_id)
    await ctx.principal.session.delete(m)
    await ctx.principal.session.flush()
    await audit.record(ctx.principal.session, "org.member_removed", actor_id=ctx.principal.id, org_id=ctx.org.id,
                       target_type="user", target_id=user_id, request=request)
    return Response(status_code=204)


# ---------------------------------------------------------------- teams
@router.get("/orgs/{org_id}/teams", response_model=list[TeamOut])
async def list_teams(ctx: OrgCtx = Depends(org_ctx)):
    return (await ctx.principal.session.execute(select(Team).where(Team.org_id == ctx.org.id).order_by(Team.name))).scalars().all()


@router.post("/orgs/{org_id}/teams", response_model=TeamOut, status_code=201)
async def create_team(body: TeamIn, request: Request, ctx: OrgCtx = Depends(org_ctx)):
    ctx.require("org.teams.manage")
    s = ctx.principal.session
    if (await s.execute(select(Team.id).where(Team.org_id == ctx.org.id, Team.name == body.name))).first():
        raise AppError(409, "team_exists", "A team with that name exists")
    team = Team(org_id=ctx.org.id, name=body.name)
    s.add(team)
    await s.flush()
    await s.refresh(team)
    await audit.record(s, "team.created", actor_id=ctx.principal.id, org_id=ctx.org.id, target_type="team",
                       target_id=team.id, request=request)
    return team


@router.post("/orgs/{org_id}/teams/{team_id}/members", status_code=204)
async def add_team_member(team_id: uuid.UUID, body: TeamMemberIn, request: Request, ctx: OrgCtx = Depends(org_ctx)):
    ctx.require("org.teams.manage")
    s = ctx.principal.session
    team = await s.get(Team, team_id)
    if team is None or team.org_id != ctx.org.id:
        raise not_found("team")
    if await s.get(OrgMember, (ctx.org.id, body.user_id)) is None:
        raise AppError(422, "not_org_member", "Not an organisation member", "Add them to the organisation first.")
    if await s.get(TeamMember, (team_id, body.user_id)) is None:
        s.add(TeamMember(team_id=team_id, org_id=ctx.org.id, user_id=body.user_id))
        await s.flush()
        await audit.record(s, "team.member_added", actor_id=ctx.principal.id, org_id=ctx.org.id, target_type="team",
                           target_id=team_id, metadata={"user_id": str(body.user_id)}, request=request)
    return Response(status_code=204)


# ---------------------------------------------------------------- product access
@router.get("/orgs/{org_id}/products", response_model=list[ProductOut])
async def list_products(ctx: OrgCtx = Depends(org_ctx)):
    return (await ctx.principal.session.execute(select(ProductAccess).where(ProductAccess.org_id == ctx.org.id)
                                                .order_by(ProductAccess.product))).scalars().all()


@router.post("/orgs/{org_id}/products", response_model=ProductOut, status_code=201)
async def enrol_product(body: ProductIn, request: Request, ctx: OrgCtx = Depends(org_ctx)):
    ctx.require("org.products.manage")
    s = ctx.principal.session
    pa = await s.get(ProductAccess, (ctx.org.id, body.product))
    if pa is None:
        pa = ProductAccess(org_id=ctx.org.id, product=body.product, status="active")
        s.add(pa)
        await s.flush()
        await audit.record(s, "org.product_enrolled", actor_id=ctx.principal.id, org_id=ctx.org.id,
                           target_type="product", target_id=body.product, request=request)
    return pa
