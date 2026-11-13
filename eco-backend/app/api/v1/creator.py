"""Creator & Marketing division API.

Three routers:
  - `clients`: onboarding and the multi-client list (account level)
  - `router`:  everything inside one client workspace (/v1/workspaces/{id}/creator/...)
  - `public`:  the client review page reached by a review link (no account; token-scoped, system context)

Nothing here publishes to a platform or fetches analytics. "Published" in the calendar means a person posted it
themselves and recorded it; performance figures are entered by hand or uploaded as CSV.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.ai import orchestrator
from app.ai.context import AgentContext
from app.ai.orchestrator import RunRequest
from app.ai.providers import get_embedder, get_llm_provider
from app.ai.providers.base import LLMProvider
from app.ai.research import get_research_backend
from app.api.v1.workspaces import create_workspace_row
from app.core.db import transaction
from app.core.deps import Principal, WsCtx, get_principal, ws_ctx
from app.core.errors import AppError, forbidden, not_found
from app.core.security import hash_token
from app.models import (
    AgentRun,
    Asset,
    AssetComment,
    AssetVersion,
    CalendarItem,
    Campaign,
    ClientAccount,
    Conversation,
    FollowerSnapshot,
    Organisation,
    OrgMember,
    PostMetric,
    ProductAccess,
    ReviewLink,
    Workspace,
)
from app.schemas.common import AssetOut, ExchangeOut, MessageOut, RunSummaryOut
from app.schemas.creator import (
    ApplyBrandIn,
    CalendarItemIn,
    CalendarItemOut,
    CalendarItemPatch,
    CampaignDetail,
    CampaignIn,
    CampaignOut,
    CampaignPatch,
    ClientSummary,
    CommentIn,
    CommentOut,
    DecisionIn,
    FollowersIn,
    FollowersOut,
    GenerateIn,
    ImportCalendarIn,
    MarkPublishedIn,
    MetricIn,
    MetricOut,
    NewClientIn,
    OnboardingIn,
    OnboardingState,
    PublicDecisionIn,
    ReviewLinkCreated,
    ReviewLinkIn,
    ReviewLinkOut,
    SaveDraftsIn,
    SubmitIn,
)
from app.services import audit, billing
from app.services import creator as svc
from app.services.storage import content_disposition

clients = APIRouter(prefix="/v1/creator", tags=["creator"])
router = APIRouter(prefix="/v1/workspaces/{workspace_id}/creator", tags=["creator"])
public = APIRouter(prefix="/v1/review", tags=["client review"])

STUDIO_AGENT = {"content": "creator.content_writer", "brand_voice": "creator.brand_strategist",
                "calendar": "creator.calendar_planner", "campaign": "creator.campaign_planner",
                "research": "creator.research_analyst", "report": "creator.report_writer"}
STUDIO_TITLE_PREFIX = "Studio · "
FORMAT_TO_ASSET = {"post": "post", "thread": "thread", "caption": "caption", "reel_script": "script",
                   "carousel": "post", "story": "post"}


# ====================================================================== helpers
def _creator(ctx: WsCtx) -> None:
    if ctx.workspace.product != "creator":
        raise AppError(409, "wrong_product", "Not a Creator workspace",
                       "These tools are for Creator & Marketing workspaces.")


async def creator_ctx(ctx: WsCtx = Depends(ws_ctx)) -> WsCtx:
    _creator(ctx)
    return ctx


def _completeness(ca: ClientAccount | None) -> int:
    if ca is None:
        return 0
    checks = [bool(ca.client_name), bool(ca.industry), bool(ca.website), bool((ca.business_info or {}).get("description")),
              bool(ca.platforms), bool(ca.brand_voice), bool((ca.audience or {}).get("summary") or
                                                               (ca.audience or {}).get("personas")),
              bool(ca.goals), bool(ca.competitors), bool(ca.content_pillars)]
    return round(100 * sum(checks) / len(checks))


def _tz(p: Principal) -> ZoneInfo:
    try:
        return ZoneInfo(p.user.timezone or "UTC")
    except Exception:
        return ZoneInfo("UTC")


async def _get_in_ws(ctx: WsCtx, model, obj_id: uuid.UUID, what: str):
    obj = await ctx.session.get(model, obj_id)
    if obj is None or obj.workspace_id != ctx.workspace.id or getattr(obj, "deleted_at", None) is not None:
        raise not_found(what)
    return obj


async def _audit(ctx: WsCtx, action: str, target_type: str, target_id, **meta) -> None:
    await audit.record(ctx.session, action, actor_id=ctx.principal.id, org_id=ctx.workspace.org_id,
                       workspace_id=ctx.workspace.id, target_type=target_type, target_id=target_id,
                       metadata=meta or None, request=ctx.request)


def _download(data: bytes, filename: str, media: str) -> Response:
    return Response(content=data, media_type=media,
                    headers={"Content-Disposition": content_disposition(filename),
                             "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


def _safe_name(s: str) -> str:
    # Unicode letters are fine here: content_disposition() handles the header encoding
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in s)[:60].strip("-") or "export"


# ====================================================================== onboarding & clients
async def _client_rows(p: Principal) -> list[ClientSummary]:
    rows = (await p.session.execute(
        select(Workspace, Organisation, ClientAccount, func.app.ws_role(Workspace.id))
        .join(Organisation, Organisation.id == Workspace.org_id)
        .outerjoin(ClientAccount, ClientAccount.workspace_id == Workspace.id)
        .where(Workspace.product == "creator", Workspace.deleted_at.is_(None))
        .order_by(Workspace.created_at))).all()
    out = []
    for ws, org, ca, role in rows:
        if role not in ("admin", "editor", "viewer"):
            continue
        out.append(ClientSummary(workspace_id=ws.id, workspace_name=ws.name, org_id=org.id, org_name=org.name,
                                 org_kind=org.kind, role=role, client_name=ca.client_name if ca else None,
                                 industry=ca.industry if ca else None, platforms=list(ca.platforms) if ca else [],
                                 profile_complete=_completeness(ca), created_at=ws.created_at))
    return out


@clients.get("/onboarding", response_model=OnboardingState)
async def onboarding_state(p: Principal = Depends(get_principal)):
    orgs = (await p.session.execute(
        select(Organisation, OrgMember.role).join(OrgMember, OrgMember.org_id == Organisation.id)
        .where(OrgMember.user_id == p.id, Organisation.deleted_at.is_(None)).order_by(Organisation.created_at))).all()
    org_list = []
    for org, role in orgs:
        ent = await billing.entitlements(p.session, org.id)
        has = await p.session.get(ProductAccess, (org.id, "creator")) is not None
        org_list.append({"id": str(org.id), "name": org.name, "kind": org.kind, "role": role, "plan": ent.plan.code,
                         "max_workspaces": ent.plan.max_workspaces, "creator_enabled": has})
    rows = await _client_rows(p)
    return OnboardingState(has_creator_workspace=bool(rows), orgs=org_list, clients=rows,
                           next_step="done" if rows else "create_first_client")


async def _enable_creator(p: Principal, org: Organisation, request: Request) -> None:
    if await p.session.get(ProductAccess, (org.id, "creator")) is None:
        p.session.add(ProductAccess(org_id=org.id, product="creator", status="active"))
        await p.session.flush()
        await audit.record(p.session, "org.product_enrolled", actor_id=p.id, org_id=org.id, target_type="product",
                           target_id="creator", request=request)


async def _create_client(p: Principal, org: Organisation, body, request: Request) -> Workspace:
    ws = await create_workspace_row(p, org, body.client_name[:120], "creator", request)
    data = body.model_dump(mode="json")
    p.session.add(ClientAccount(workspace_id=ws.id, org_id=org.id, **data))
    await p.session.flush()
    await audit.record(p.session, "profile.client_account_saved", actor_id=p.id, org_id=org.id, workspace_id=ws.id,
                       target_type="workspace", target_id=ws.id, request=request)
    return ws


async def _org_admin(p: Principal, org_id: uuid.UUID) -> Organisation:
    org = await p.session.get(Organisation, org_id)
    role = (await p.session.execute(select(OrgMember.role).where(OrgMember.org_id == org_id,
                                                                 OrgMember.user_id == p.id))).scalar_one_or_none()
    if org is None or role is None or org.deleted_at is not None:
        raise not_found("org")
    if role not in ("owner", "admin"):
        raise forbidden("Only organisation owners and admins can add clients.")
    return org


@clients.post("/onboarding", status_code=201)
async def complete_onboarding(body: OnboardingIn, request: Request, p: Principal = Depends(get_principal)):
    """Sets up the Creator division in one step: picks (solo) or creates (agency) the organisation, turns the
    product on, and creates the first client workspace with its profile."""
    if body.mode == "solo":
        org = (await p.session.execute(select(Organisation).where(
            Organisation.owner_user_id == p.id, Organisation.kind == "personal",
            Organisation.deleted_at.is_(None)))).scalar_one()
    else:
        org = Organisation(name=body.agency_name, kind="team", owner_user_id=p.id)
        p.session.add(org)
        await p.session.flush()
        p.session.add(OrgMember(org_id=org.id, user_id=p.id, role="owner"))
        await p.session.flush()
        await audit.record(p.session, "org.created", actor_id=p.id, org_id=org.id, target_type="org",
                           target_id=org.id, request=request)
    await _enable_creator(p, org, request)
    ws = await _create_client(p, org, body.client, request)
    return {"org_id": str(org.id), "workspace_id": str(ws.id)}


@clients.get("/clients", response_model=list[ClientSummary])
async def list_clients(p: Principal = Depends(get_principal)):
    return await _client_rows(p)


@clients.post("/clients", status_code=201)
async def add_client(body: NewClientIn, request: Request, p: Principal = Depends(get_principal)):
    org = await _org_admin(p, body.org_id)
    await _enable_creator(p, org, request)
    ws = await _create_client(p, org, body.client, request)
    return {"org_id": str(org.id), "workspace_id": str(ws.id)}


@clients.get("/capabilities")
async def capabilities():
    """What works today and what needs a platform integration. Shown in the app so nobody is misled."""
    return {"features": svc.CAPABILITIES, "platforms": svc.PLATFORM_INTEGRATIONS}


# ====================================================================== overview (dashboard)
@router.get("/overview")
async def overview(ctx: WsCtx = Depends(creator_ctx)):
    s, ws = ctx.session, ctx.workspace
    now = datetime.now(UTC)
    ca = (await s.execute(select(ClientAccount).where(ClientAccount.workspace_id == ws.id))).scalar_one_or_none()
    status_counts = dict((await s.execute(select(Asset.status, func.count()).where(
        Asset.workspace_id == ws.id, Asset.deleted_at.is_(None)).group_by(Asset.status))).all())
    upcoming = (await s.execute(select(CalendarItem).where(
        CalendarItem.workspace_id == ws.id, CalendarItem.scheduled_for >= now,
        CalendarItem.scheduled_for < now + timedelta(days=7)).order_by(CalendarItem.scheduled_for).limit(10))).scalars().all()
    overdue = (await s.execute(select(func.count()).select_from(CalendarItem).where(
        CalendarItem.workspace_id == ws.id, CalendarItem.scheduled_for < now,
        CalendarItem.status.in_(("planned", "drafted", "ready"))))).scalar_one()
    recent = (await s.execute(select(Asset).where(Asset.workspace_id == ws.id, Asset.deleted_at.is_(None))
                              .order_by(Asset.updated_at.desc()).limit(6))).scalars().all()
    campaigns = (await s.execute(select(Campaign).where(Campaign.workspace_id == ws.id,
                                                        Campaign.status.in_(("draft", "active")))
                                 .order_by(Campaign.created_at.desc()).limit(5))).scalars().all()
    metrics_count = (await s.execute(select(func.count()).select_from(PostMetric).where(
        PostMetric.workspace_id == ws.id))).scalar_one()
    cal_count = (await s.execute(select(func.count()).select_from(CalendarItem).where(
        CalendarItem.workspace_id == ws.id))).scalar_one()
    ent = await billing.entitlements(s, ws.org_id)
    used = None if ent.is_paid_active else await billing.free_used(s, ws.org_id)
    checklist = [
        {"key": "profile", "label": "Complete the client profile", "done": _completeness(ca) >= 70},
        {"key": "brand_voice", "label": "Set the brand voice", "done": bool(ca and ca.brand_voice)},
        {"key": "first_draft", "label": "Save a first draft", "done": sum(status_counts.values()) > 0},
        {"key": "calendar", "label": "Plan the content calendar", "done": cal_count > 0},
        {"key": "approval", "label": "Get something approved",
         "done": status_counts.get("approved", 0) + status_counts.get("posted", 0) > 0},
        {"key": "metrics", "label": "Record performance figures", "done": metrics_count > 0},
    ]
    return {
        "workspace": {"id": str(ws.id), "name": ws.name, "role": ctx.role},
        "client": {"name": ca.client_name if ca else ws.name, "platforms": list(ca.platforms) if ca else [],
                   "profile_complete": _completeness(ca)},
        "content": {s_: status_counts.get(s_, 0) for s_ in ("draft", "in_review", "approved", "posted", "archived")},
        "calendar": {"upcoming": [CalendarItemOut.model_validate(i).model_dump(mode="json") for i in upcoming],
                     "overdue": overdue},
        "campaigns": [CampaignOut.model_validate(c).model_dump(mode="json") for c in campaigns],
        "recent": [AssetOut.model_validate(a).model_dump(mode="json") for a in recent],
        "plan": {"code": ent.plan.code, "name": ent.plan.name, "ai_unlimited": ent.is_paid_active,
                 "free_used": used, "free_limit": ent.plan.free_monthly_limit,
                 "free_remaining": None if used is None else max(0, (ent.plan.free_monthly_limit or 0) - used)},
        "checklist": checklist,
        "integrations": {"publishing": "requires_integration", "analytics": "youtube_only"},
    }


# ====================================================================== studio (AI generation)
@router.post("/generate", response_model=ExchangeOut, status_code=201)
async def generate(body: GenerateIn, ctx: WsCtx = Depends(creator_ctx),
                   provider: LLMProvider = Depends(get_llm_provider), embedder=Depends(get_embedder),
                   research=Depends(get_research_backend)):
    """Run a Creator studio tool. Each run gets its own conversation (titled 'Studio · …') so earlier drafts don't
    leak into a new brief; the output is structured and can be saved, edited and applied."""
    await ctx.require("ws.ai.run")
    s = ctx.session
    ca = (await s.execute(select(ClientAccount).where(ClientAccount.workspace_id == ctx.workspace.id))).scalar_one_or_none()
    platforms = list(body.platforms) or (list(ca.platforms) if ca and ca.platforms else [])
    extra = ""
    if body.kind == "report":
        summary = await _summary(ctx, body.start_date, body.end_date)
        extra = svc.summary_text(summary)
    message = svc.studio_message(body.kind, body.brief,
                                 platforms=platforms if body.kind in ("content", "calendar", "campaign") else None,
                                 formats=body.formats or None, count=body.count if body.kind == "content" else None,
                                 start=body.start_date, end=body.end_date, extra=extra)
    conv = Conversation(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, created_by=ctx.principal.id,
                        title=f"{STUDIO_TITLE_PREFIX}{body.kind}: {body.brief[:60]}")
    s.add(conv)
    await s.flush()
    actx = AgentContext(session=s, user_id=ctx.principal.id, org_id=ctx.workspace.org_id,
                        workspace_id=ctx.workspace.id, workspace_name=ctx.workspace.name, product="creator",
                        role=ctx.role, provider=provider, embedder=embedder, research=research,
                        conversation_id=conv.id, request=ctx.request)
    result = await orchestrator.run(actx, RunRequest(message=message, conversation=conv, agent=STUDIO_AGENT[body.kind],
                                                     document_ids=body.document_ids, save=body.save))
    r = result.run
    return ExchangeOut(user_message=MessageOut.model_validate(result.user_message),
                       assistant_message=MessageOut.model_validate(result.assistant_message),
                       run=RunSummaryOut(id=r.id, agent=r.agent, status=r.status, output=result.output,
                                         warnings=r.warnings, uncertainties=r.uncertainties,
                                         injection_detected=bool(r.injection_flags),
                                         pending_actions=result.pending_actions, saved_asset_id=result.saved_asset_id,
                                         memory_saved=result.memory_saved))


async def _run_output(ctx: WsCtx, run_id: uuid.UUID, agent: str) -> tuple[AgentRun, dict]:
    run = await ctx.session.get(AgentRun, run_id)
    if run is None or run.workspace_id != ctx.workspace.id:
        raise not_found("run")
    if run.agent != agent or run.status != "succeeded" or not run.output:
        raise AppError(409, "wrong_run", "Can't use that result", f"That result isn't a finished {agent} output.")
    return run, run.output


@router.post("/runs/{run_id}/save-drafts", response_model=list[AssetOut], status_code=201)
async def save_drafts(run_id: uuid.UUID, body: SaveDraftsIn, ctx: WsCtx = Depends(creator_ctx)):
    """Save chosen drafts from a content run as separate, editable library items (status: draft)."""
    await ctx.require("ws.write")
    run, out = await _run_output(ctx, run_id, "creator.content_writer")
    drafts = out.get("drafts", [])
    idx = body.indexes if body.indexes is not None else list(range(len(drafts)))
    if not idx or any(i < 0 or i >= len(drafts) for i in idx):
        raise AppError(422, "bad_indexes", "Pick drafts that exist", f"This result has {len(drafts)} draft(s).")
    from app.ai.agents.specs import ContentPack
    saved = []
    for i in dict.fromkeys(idx):
        d = drafts[i]
        text_ = ContentPack.model_validate({**out, "drafts": [d]}).render().split("\n\n", 1)[1]
        a = Asset(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id,
                  type=FORMAT_TO_ASSET.get(d["format"], "post"), title=(d["hook"] or d["body"])[:120],
                  tags=[d["platform"]], created_by=ctx.principal.id)
        ctx.session.add(a)
        await ctx.session.flush()
        ctx.session.add(AssetVersion(asset_id=a.id, workspace_id=a.workspace_id, org_id=a.org_id, version=1,
                                     body={**d, "run_id": str(run.id)}, body_text=text_, source="ai",
                                     author_id=ctx.principal.id))
        saved.append(a)
    await ctx.session.flush()
    for a in saved:
        await ctx.session.refresh(a)
    await _audit(ctx, "creator.drafts_saved", "agent_run", run.id, count=len(saved))
    return saved


@router.post("/runs/{run_id}/apply-brand")
async def apply_brand(run_id: uuid.UUID, body: ApplyBrandIn, ctx: WsCtx = Depends(creator_ctx)):
    """Apply chosen parts of a brand strategy run to the client profile. Nothing is applied automatically."""
    await ctx.require("ws.write")
    run, out = await _run_output(ctx, run_id, "creator.brand_strategist")
    ca = (await ctx.session.execute(select(ClientAccount).where(
        ClientAccount.workspace_id == ctx.workspace.id))).scalar_one_or_none()
    if ca is None:
        raise AppError(409, "no_profile", "Add the client profile first", "Save the client profile before applying.")
    if "voice" in body.parts:
        ca.brand_voice = {**(ca.brand_voice or {}), "attributes": out["voice_attributes"],
                          "tone_by_platform": out["tone_by_platform"], "words_to_use": out["words_to_use"],
                          "words_to_avoid": out["words_to_avoid"], "sample_lines": out["sample_lines"]}
    if "positioning" in body.parts:
        ca.brand_voice = {**(ca.brand_voice or {}), "positioning": out["positioning"]}
    if "personas" in body.parts:
        ca.audience = {**(ca.audience or {}), "personas": out["audience_personas"]}
    if "pillars" in body.parts:
        ca.content_pillars = out["content_pillars"]
    ca.version += 1
    await ctx.session.flush()
    await _audit(ctx, "creator.brand_applied", "agent_run", run.id, parts=body.parts)
    return {"applied": body.parts, "version": ca.version}


@router.post("/runs/{run_id}/import-calendar", response_model=list[CalendarItemOut], status_code=201)
async def import_calendar(run_id: uuid.UUID, body: ImportCalendarIn, ctx: WsCtx = Depends(creator_ctx)):
    await ctx.require("ws.write")
    run, out = await _run_output(ctx, run_id, "creator.calendar_planner")
    items = out.get("items", [])
    idx = body.indexes if body.indexes is not None else list(range(len(items)))
    if not idx or any(i < 0 or i >= len(items) for i in idx):
        raise AppError(422, "bad_indexes", "Pick items that exist", f"This plan has {len(items)} item(s).")
    if body.campaign_id:
        await _get_in_ws(ctx, Campaign, body.campaign_id, "campaign")
    tz = _tz(ctx.principal)
    created = []
    for i in dict.fromkeys(idx):
        it = items[i]
        hh, mm = (int(x) for x in it["time"].split(":"))
        when = datetime.combine(date.fromisoformat(it["date"]), time(hh, mm), tzinfo=tz)
        c = CalendarItem(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, campaign_id=body.campaign_id,
                         title=it["title"][:200], platform=it["platform"], format=it["format"], pillar=it["pillar"][:80],
                         notes=it["idea"][:4000], scheduled_for=when, source="ai_plan", source_run_id=run.id,
                         created_by=ctx.principal.id)
        ctx.session.add(c)
        created.append(c)
    await ctx.session.flush()
    for c in created:
        await ctx.session.refresh(c)
    await _audit(ctx, "creator.calendar_imported", "agent_run", run.id, count=len(created))
    return created


@router.post("/runs/{run_id}/create-campaign", response_model=CampaignOut, status_code=201)
async def campaign_from_run(run_id: uuid.UUID, ctx: WsCtx = Depends(creator_ctx)):
    await ctx.require("ws.write")
    run, out = await _run_output(ctx, run_id, "creator.campaign_planner")
    c = Campaign(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, name=out["name"][:160],
                 objective=out["objective"][:1000], start_date=date.fromisoformat(out["start_date"]),
                 end_date=date.fromisoformat(out["end_date"]), channels=out["channels"],
                 budget_note=out["budget_note"][:1000], plan=out, source_run_id=run.id, created_by=ctx.principal.id)
    ctx.session.add(c)
    await ctx.session.flush()
    await ctx.session.refresh(c)
    await _audit(ctx, "campaign.created", "campaign", c.id, from_run=str(run.id))
    return c


# ====================================================================== calendar
async def _with_assets(ctx: WsCtx, items: list[CalendarItem]) -> list[CalendarItemOut]:
    ids = [i.asset_id for i in items if i.asset_id]
    assets = {}
    if ids:
        assets = {a.id: a for a in (await ctx.session.execute(select(Asset).where(Asset.id.in_(ids)))).scalars()}
    out = []
    for i in items:
        o = CalendarItemOut.model_validate(i)
        a = assets.get(i.asset_id)
        if a is not None and a.deleted_at is None:
            o.asset_title, o.asset_status = a.title, a.status
        out.append(o)
    return out


def _range(start: date | None, end: date | None, default_days: int = 31, max_days: int = 400) -> tuple[date, date]:
    start = start or date.today().replace(day=1)
    end = end or start + timedelta(days=default_days)
    if end < start or (end - start).days > max_days:
        raise AppError(400, "bad_range", "Invalid date range", f"Use a range of up to {max_days} days.")
    return start, end


@router.get("/calendar", response_model=list[CalendarItemOut])
async def list_calendar(start: date | None = None, end: date | None = None, campaign_id: uuid.UUID | None = None,
                        ctx: WsCtx = Depends(creator_ctx)):
    start, end = _range(start, end)
    tz = _tz(ctx.principal)
    lo = datetime.combine(start, time.min, tzinfo=tz)
    hi = datetime.combine(end, time.max, tzinfo=tz)
    stmt = select(CalendarItem).where(CalendarItem.workspace_id == ctx.workspace.id,
                                      CalendarItem.scheduled_for >= lo, CalendarItem.scheduled_for <= hi)
    if campaign_id:
        stmt = stmt.where(CalendarItem.campaign_id == campaign_id)
    items = (await ctx.session.execute(stmt.order_by(CalendarItem.scheduled_for).limit(1000))).scalars().all()
    return await _with_assets(ctx, list(items))


async def _check_links(ctx: WsCtx, asset_id, campaign_id) -> None:
    if asset_id:
        await _get_in_ws(ctx, Asset, asset_id, "asset")
    if campaign_id:
        await _get_in_ws(ctx, Campaign, campaign_id, "campaign")


@router.post("/calendar", response_model=CalendarItemOut, status_code=201)
async def create_calendar_item(body: CalendarItemIn, ctx: WsCtx = Depends(creator_ctx)):
    await ctx.require("ws.write")
    await _check_links(ctx, body.asset_id, body.campaign_id)
    when = body.scheduled_for if body.scheduled_for.tzinfo else body.scheduled_for.replace(tzinfo=_tz(ctx.principal))
    c = CalendarItem(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, created_by=ctx.principal.id,
                     **body.model_dump(exclude={"scheduled_for"}), scheduled_for=when,
                     status="drafted" if body.asset_id else "planned")
    ctx.session.add(c)
    await ctx.session.flush()
    await ctx.session.refresh(c)
    return (await _with_assets(ctx, [c]))[0]


@router.patch("/calendar/{item_id}", response_model=CalendarItemOut)
async def update_calendar_item(item_id: uuid.UUID, body: CalendarItemPatch, ctx: WsCtx = Depends(creator_ctx)):
    await ctx.require("ws.write")
    c = await _get_in_ws(ctx, CalendarItem, item_id, "calendar item")
    changes = body.model_dump(exclude_unset=True)
    await _check_links(ctx, changes.get("asset_id"), changes.get("campaign_id"))
    if "scheduled_for" in changes and changes["scheduled_for"].tzinfo is None:
        changes["scheduled_for"] = changes["scheduled_for"].replace(tzinfo=_tz(ctx.principal))
    if "status" in changes and c.status == "published_manually":
        c.published_at, c.published_url = None, None  # un-marking a manual publish
    for k, v in changes.items():
        setattr(c, k, v)
    await ctx.session.flush()
    await ctx.session.refresh(c)
    return (await _with_assets(ctx, [c]))[0]


@router.post("/calendar/{item_id}/mark-published", response_model=CalendarItemOut)
async def mark_published(item_id: uuid.UUID, body: MarkPublishedIn, ctx: WsCtx = Depends(creator_ctx)):
    """Record that someone posted this themselves. This doesn't post anything and isn't verified against the
    platform. If content is linked, it must be approved first, and it moves to 'posted'."""
    await ctx.require("ws.write")
    c = await _get_in_ws(ctx, CalendarItem, item_id, "calendar item")
    if c.asset_id:
        a = await ctx.session.get(Asset, c.asset_id)
        if a is not None and a.deleted_at is None:
            if a.status not in ("approved", "posted"):
                raise AppError(409, "not_approved", "Approve it first",
                               "The linked content hasn't been approved, so it can't be marked as published.")
            a.status = "posted"
    c.status, c.published_url = "published_manually", body.published_url
    c.published_at = body.published_at or datetime.now(UTC)
    await ctx.session.flush()
    await ctx.session.refresh(c)
    await _audit(ctx, "calendar.marked_published", "calendar_item", c.id, manual=True, has_url=bool(body.published_url))
    return (await _with_assets(ctx, [c]))[0]


@router.delete("/calendar/{item_id}", status_code=204)
async def delete_calendar_item(item_id: uuid.UUID, ctx: WsCtx = Depends(creator_ctx)):
    await ctx.require("ws.write")
    c = await _get_in_ws(ctx, CalendarItem, item_id, "calendar item")
    await ctx.session.delete(c)
    return Response(status_code=204)


@router.get("/calendar/export")
async def export_calendar(format: str = Query(pattern="^(csv|ics)$"), start: date | None = None,
                          end: date | None = None, ctx: WsCtx = Depends(creator_ctx)):
    items = await list_calendar(start, end, None, ctx)
    name = _safe_name(ctx.workspace.name)
    if format == "ics":
        return _download(svc.ics_bytes(items, f"{ctx.workspace.name} content calendar"), f"{name}-calendar.ics",
                         "text/calendar")
    rows = [[i.scheduled_for.isoformat(), i.platform, i.format, i.title, i.pillar or "", i.status, i.asset_title or "",
             i.published_url or "", i.notes] for i in items]
    return _download(svc.csv_bytes(["scheduled_for", "platform", "format", "title", "pillar", "status", "content",
                                    "published_url", "notes"], rows), f"{name}-calendar.csv", "text/csv")


# ====================================================================== campaigns
@router.get("/campaigns", response_model=list[CampaignOut])
async def list_campaigns(status: str | None = None, ctx: WsCtx = Depends(creator_ctx)):
    stmt = select(Campaign).where(Campaign.workspace_id == ctx.workspace.id)
    if status:
        stmt = stmt.where(Campaign.status == status)
    return (await ctx.session.execute(stmt.order_by(Campaign.created_at.desc()).limit(200))).scalars().all()


@router.post("/campaigns", response_model=CampaignOut, status_code=201)
async def create_campaign(body: CampaignIn, ctx: WsCtx = Depends(creator_ctx)):
    await ctx.require("ws.write")
    c = Campaign(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, created_by=ctx.principal.id,
                 **body.model_dump())
    ctx.session.add(c)
    await ctx.session.flush()
    await ctx.session.refresh(c)
    await _audit(ctx, "campaign.created", "campaign", c.id)
    return c


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetail)
async def get_campaign(campaign_id: uuid.UUID, ctx: WsCtx = Depends(creator_ctx)):
    c = await _get_in_ws(ctx, Campaign, campaign_id, "campaign")
    items = (await ctx.session.execute(select(CalendarItem).where(CalendarItem.campaign_id == c.id)
                                       .order_by(CalendarItem.scheduled_for))).scalars().all()
    detail = CampaignDetail.model_validate(c)
    detail.calendar = await _with_assets(ctx, list(items))
    detail.counts = {st: sum(1 for i in items if i.status == st) for st in
                     ("planned", "drafted", "ready", "published_manually", "skipped")}
    return detail


@router.patch("/campaigns/{campaign_id}", response_model=CampaignOut)
async def update_campaign(campaign_id: uuid.UUID, body: CampaignPatch, ctx: WsCtx = Depends(creator_ctx)):
    await ctx.require("ws.write")
    c = await _get_in_ws(ctx, Campaign, campaign_id, "campaign")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    if c.start_date and c.end_date and c.end_date < c.start_date:
        raise AppError(422, "bad_dates", "Check the dates", "The end date is before the start date.")
    await ctx.session.flush()
    await ctx.session.refresh(c)
    return c


@router.delete("/campaigns/{campaign_id}", status_code=204)
async def delete_campaign(campaign_id: uuid.UUID, ctx: WsCtx = Depends(creator_ctx)):
    await ctx.require("ws.write")
    c = await _get_in_ws(ctx, Campaign, campaign_id, "campaign")
    await ctx.session.delete(c)  # calendar items keep existing, unlinked
    await _audit(ctx, "campaign.deleted", "campaign", c.id)
    return Response(status_code=204)


# ====================================================================== approvals
async def _comment(ctx: WsCtx, a: Asset, kind: str, body: str) -> AssetComment:
    cm = AssetComment(workspace_id=a.workspace_id, org_id=a.org_id, asset_id=a.id, asset_version=a.current_version,
                      kind=kind, body=body, via="team", author_user_id=ctx.principal.id)
    ctx.session.add(cm)
    await ctx.session.flush()
    await ctx.session.refresh(cm)
    return cm


@router.get("/approvals")
async def approvals(ctx: WsCtx = Depends(creator_ctx)):
    rows = (await ctx.session.execute(select(Asset).where(
        Asset.workspace_id == ctx.workspace.id, Asset.deleted_at.is_(None), Asset.status == "in_review")
        .order_by(Asset.updated_at))).scalars().all()
    last = {}
    if rows:
        cms = (await ctx.session.execute(select(AssetComment).where(AssetComment.asset_id.in_([a.id for a in rows]))
                                         .order_by(AssetComment.created_at))).scalars().all()
        for cm in cms:
            last[cm.asset_id] = CommentOut.model_validate(cm).model_dump(mode="json")
    links = (await ctx.session.execute(select(ReviewLink).where(
        ReviewLink.workspace_id == ctx.workspace.id, ReviewLink.revoked_at.is_(None),
        ReviewLink.expires_at > datetime.now(UTC)).order_by(ReviewLink.created_at.desc()))).scalars().all()
    return {"in_review": [{**AssetOut.model_validate(a).model_dump(mode="json"), "last_comment": last.get(a.id)}
                          for a in rows],
            "review_links": [ReviewLinkOut.model_validate(l).model_dump(mode="json") for l in links],
            "can_approve": ctx.role == "admin"}


@router.post("/assets/{asset_id}/submit", response_model=AssetOut)
async def submit_for_review(asset_id: uuid.UUID, body: SubmitIn, ctx: WsCtx = Depends(creator_ctx)):
    await ctx.require("ws.write")
    a = await _get_in_ws(ctx, Asset, asset_id, "asset")
    if a.status not in ("draft", "in_review"):
        raise AppError(409, "bad_status", "Can't submit this", f"It's {a.status.replace('_', ' ')}.")
    a.status = "in_review"
    await _comment(ctx, a, "submitted", body.note)
    await ctx.session.refresh(a)
    await _audit(ctx, "asset.submitted", "asset", a.id)
    return a


@router.post("/assets/{asset_id}/decision", response_model=AssetOut)
async def decide(asset_id: uuid.UUID, body: DecisionIn, ctx: WsCtx = Depends(creator_ctx)):
    await ctx.require("ws.write")
    a = await _get_in_ws(ctx, Asset, asset_id, "asset")
    if body.decision == "approve" and ctx.role != "admin":
        raise AppError(403, "approval_required", "Approval needed", "Only a workspace admin can approve.")
    if a.status != "in_review":
        raise AppError(409, "bad_status", "Not in review", "Submit it for review first.")
    a.status = "approved" if body.decision == "approve" else "draft"
    await _comment(ctx, a, "approved" if body.decision == "approve" else "changes_requested", body.comment)
    await ctx.session.refresh(a)
    await _audit(ctx, f"asset.{'approved' if body.decision == 'approve' else 'changes_requested'}", "asset", a.id,
                 version=a.current_version)
    return a


@router.get("/assets/{asset_id}/comments", response_model=list[CommentOut])
async def list_comments(asset_id: uuid.UUID, ctx: WsCtx = Depends(creator_ctx)):
    await _get_in_ws(ctx, Asset, asset_id, "asset")
    return (await ctx.session.execute(select(AssetComment).where(AssetComment.asset_id == asset_id)
                                      .order_by(AssetComment.created_at))).scalars().all()


@router.post("/assets/{asset_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(asset_id: uuid.UUID, body: CommentIn, ctx: WsCtx = Depends(creator_ctx)):
    a = await _get_in_ws(ctx, Asset, asset_id, "asset")
    return await _comment(ctx, a, "comment", body.body)


@router.post("/review-links", response_model=ReviewLinkCreated, status_code=201)
async def create_review_link(body: ReviewLinkIn, ctx: WsCtx = Depends(creator_ctx)):
    """Share chosen items with a client who has no account. The token is shown once; only its hash is kept."""
    await ctx.require("ws.write")
    ids = list(dict.fromkeys(body.asset_ids))
    found = (await ctx.session.execute(select(Asset.id).where(Asset.id.in_(ids), Asset.workspace_id == ctx.workspace.id,
                                                              Asset.deleted_at.is_(None)))).scalars().all()
    if len(found) != len(ids):
        raise not_found("asset")
    token = secrets.token_urlsafe(32)
    link = ReviewLink(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, token_hash=hash_token(token),
                      label=body.label, asset_ids=ids, allow_approve=body.allow_approve, created_by=ctx.principal.id,
                      expires_at=datetime.now(UTC) + timedelta(days=body.expires_in_days))
    ctx.session.add(link)
    await ctx.session.execute(Asset.__table__.update().where(Asset.id.in_(ids), Asset.status == "draft")
                              .values(status="in_review"))
    await ctx.session.flush()
    await ctx.session.refresh(link)
    await _audit(ctx, "review_link.created", "review_link", link.id, items=len(ids), days=body.expires_in_days)
    return ReviewLinkCreated(**ReviewLinkOut.model_validate(link).model_dump(), token=token)


@router.get("/review-links", response_model=list[ReviewLinkOut])
async def list_review_links(ctx: WsCtx = Depends(creator_ctx)):
    return (await ctx.session.execute(select(ReviewLink).where(ReviewLink.workspace_id == ctx.workspace.id)
                                      .order_by(ReviewLink.created_at.desc()).limit(100))).scalars().all()


@router.delete("/review-links/{link_id}", status_code=204)
async def revoke_review_link(link_id: uuid.UUID, ctx: WsCtx = Depends(creator_ctx)):
    await ctx.require("ws.write")
    link = await _get_in_ws(ctx, ReviewLink, link_id, "review link")
    link.revoked_at = datetime.now(UTC)
    await ctx.session.flush()
    await _audit(ctx, "review_link.revoked", "review_link", link.id)
    return Response(status_code=204)


# ---------------------------------------------------------------- public client review (no account)
async def _link_for(s, token: str) -> ReviewLink:
    link = (await s.execute(select(ReviewLink).where(ReviewLink.token_hash == hash_token(token)))).scalar_one_or_none()
    if link is None or link.revoked_at is not None or link.expires_at <= datetime.now(UTC):
        raise AppError(404, "link_invalid", "This review link isn't valid",
                       "It may have expired or been withdrawn. Ask the sender for a new one.")
    return link


async def _public_items(s, link: ReviewLink) -> list[dict]:
    rows = (await s.execute(select(Asset, AssetVersion).join(AssetVersion, and_(
        AssetVersion.asset_id == Asset.id, AssetVersion.version == Asset.current_version)).where(
        Asset.id.in_(link.asset_ids), Asset.workspace_id == link.workspace_id, Asset.deleted_at.is_(None)))).all()
    comments = (await s.execute(select(AssetComment).where(AssetComment.review_link_id == link.id)
                                .order_by(AssetComment.created_at))).scalars().all()
    by_asset: dict = {}
    for c in comments:
        by_asset.setdefault(c.asset_id, []).append({"kind": c.kind, "name": c.author_name, "body": c.body,
                                                    "version": c.asset_version, "at": c.created_at.isoformat()})
    order = {a: i for i, a in enumerate(link.asset_ids)}
    return sorted([{"id": str(a.id), "title": a.title, "type": a.type, "status": a.status, "version": v.version,
                    "text": v.body_text, "platform": (v.body or {}).get("platform"),
                    "feedback": by_asset.get(a.id, [])} for a, v in rows], key=lambda x: order[uuid.UUID(x["id"])])


@public.get("/{token}")
async def public_review(token: str):
    async with transaction(None, context="system") as s:
        link = await _link_for(s, token)
        ws = await s.get(Workspace, link.workspace_id)
        ca = (await s.execute(select(ClientAccount.client_name).where(
            ClientAccount.workspace_id == link.workspace_id))).scalar_one_or_none()
        link.last_viewed_at = datetime.now(UTC)
        items = await _public_items(s, link)
        return {"label": link.label, "client": ca or ws.name, "expires_at": link.expires_at.isoformat(),
                "allow_approve": link.allow_approve, "items": items}


@public.post("/{token}/assets/{asset_id}")
async def public_decision(token: str, asset_id: uuid.UUID, body: PublicDecisionIn):
    async with transaction(None, context="system") as s:
        link = await _link_for(s, token)
        if asset_id not in link.asset_ids:
            raise not_found("asset")
        a = await s.get(Asset, asset_id)
        if a is None or a.workspace_id != link.workspace_id or a.deleted_at is not None:
            raise not_found("asset")
        if body.decision == "approve" and not link.allow_approve:
            raise forbidden("This link is for comments only.")
        if body.decision == "request_changes" and not body.comment.strip():
            raise AppError(422, "comment_required", "Say what to change", "Add a comment explaining the changes.")
        kind = {"approve": "approved", "request_changes": "changes_requested", "comment": "comment"}[body.decision]
        s.add(AssetComment(workspace_id=a.workspace_id, org_id=a.org_id, asset_id=a.id, asset_version=a.current_version,
                           kind=kind, body=body.comment, via="client_link", author_name=body.name,
                           review_link_id=link.id))
        if body.decision == "approve":
            a.status = "approved"
        elif body.decision == "request_changes":
            a.status = "draft"
        await s.flush()
        await audit.record(s, f"review.client_{kind}", actor_id=None, org_id=a.org_id, workspace_id=a.workspace_id,
                           target_type="asset", target_id=a.id,
                           metadata={"review_link_id": str(link.id), "name": body.name, "version": a.current_version})
        return {"status": a.status, "items": await _public_items(s, link)}


# ====================================================================== performance & reports
@router.get("/metrics", response_model=list[MetricOut])
async def list_metrics(start: date | None = None, end: date | None = None, ctx: WsCtx = Depends(creator_ctx)):
    start, end = _range(start, end, 92)
    return (await ctx.session.execute(select(PostMetric).where(
        PostMetric.workspace_id == ctx.workspace.id, PostMetric.published_on.between(start, end))
        .order_by(PostMetric.published_on.desc(), PostMetric.created_at.desc()).limit(2000))).scalars().all()


@router.post("/metrics", response_model=MetricOut, status_code=201)
async def add_metric(body: MetricIn, ctx: WsCtx = Depends(creator_ctx)):
    await ctx.require("ws.write")
    if body.calendar_item_id:
        await _get_in_ws(ctx, CalendarItem, body.calendar_item_id, "calendar item")
    m = PostMetric(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, source="manual",
                   created_by=ctx.principal.id, **body.model_dump())
    ctx.session.add(m)
    await ctx.session.flush()
    await ctx.session.refresh(m)
    return m


@router.delete("/metrics/{metric_id}", status_code=204)
async def delete_metric(metric_id: uuid.UUID, ctx: WsCtx = Depends(creator_ctx)):
    await ctx.require("ws.write")
    await ctx.session.delete(await _get_in_ws(ctx, PostMetric, metric_id, "metric"))
    return Response(status_code=204)


@router.post("/metrics/import", status_code=201)
async def import_metrics(file: UploadFile = File(...), platform: str | None = Form(default=None),
                         ctx: WsCtx = Depends(creator_ctx)):
    """Upload a CSV exported from a platform's insights page (or filled in by hand). All rows are checked first;
    if any row is invalid, nothing is imported and every problem is listed."""
    await ctx.require("ws.write")
    data = await file.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise AppError(413, "file_too_large", "File too large", "CSV files can be up to 2 MB.")
    rows, errors = svc.parse_metrics_csv(data, platform)
    if errors:
        raise AppError(422, "csv_invalid", "Some rows need fixing", "Nothing was imported.", extra={"rows": errors[:50]})
    if not rows:
        raise AppError(422, "csv_empty", "No rows found", "The file has a header but no data rows.")
    for r in rows:
        ctx.session.add(PostMetric(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, platform=r.platform,
                                   post_label=r.post_label, published_on=r.published_on, post_url=r.post_url,
                                   source="csv_import", created_by=ctx.principal.id, **r.values))
    await ctx.session.flush()
    await _audit(ctx, "metrics.imported", "workspace", ctx.workspace.id, rows=len(rows))
    return {"imported": len(rows)}


@router.get("/followers", response_model=list[FollowersOut])
async def list_followers(ctx: WsCtx = Depends(creator_ctx)):
    return (await ctx.session.execute(select(FollowerSnapshot).where(
        FollowerSnapshot.workspace_id == ctx.workspace.id).order_by(FollowerSnapshot.captured_on.desc())
        .limit(500))).scalars().all()


@router.put("/followers", response_model=FollowersOut)
async def record_followers(body: FollowersIn, ctx: WsCtx = Depends(creator_ctx)):
    await ctx.require("ws.write")
    stmt = pg_insert(FollowerSnapshot).values(
        workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, platform=body.platform,
        captured_on=body.captured_on, followers=body.followers, source="manual", created_by=ctx.principal.id
    ).on_conflict_do_update(constraint="follower_snapshots_uq",
                            set_={"followers": body.followers, "source": "manual"}).returning(FollowerSnapshot.id)
    fid = (await ctx.session.execute(stmt)).scalar_one()
    row = await ctx.session.get(FollowerSnapshot, fid, populate_existing=True)
    return row


async def _summary(ctx: WsCtx, start: date, end: date) -> svc.ReportSummary:
    ws = ctx.workspace.id
    metrics = (await ctx.session.execute(select(PostMetric).where(
        PostMetric.workspace_id == ws, PostMetric.published_on.between(start, end)))).scalars().all()
    followers = (await ctx.session.execute(select(FollowerSnapshot).where(
        FollowerSnapshot.workspace_id == ws, FollowerSnapshot.captured_on.between(start, end)))).scalars().all()
    tz = _tz(ctx.principal)
    published = (await ctx.session.execute(select(func.count()).select_from(CalendarItem).where(
        CalendarItem.workspace_id == ws, CalendarItem.status == "published_manually",
        CalendarItem.published_at.between(datetime.combine(start, time.min, tzinfo=tz),
                                          datetime.combine(end, time.max, tzinfo=tz))))).scalar_one()
    return svc.summarise(start, end, list(metrics), list(followers), published)


@router.get("/report")
async def report(start: date, end: date, ctx: WsCtx = Depends(creator_ctx)):
    start, end = _range(start, end, max_days=366)
    return (await _summary(ctx, start, end)).as_dict()


@router.get("/report/export")
async def export_report(start: date, end: date, format: str = Query(pattern="^(csv|md|html)$"),
                        narrative_run_id: uuid.UUID | None = None, ctx: WsCtx = Depends(creator_ctx)):
    start, end = _range(start, end, max_days=366)
    summary = await _summary(ctx, start, end)
    name = f"{_safe_name(ctx.workspace.name)}-report-{start}-{end}"
    if format == "csv":
        metrics = (await ctx.session.execute(select(PostMetric).where(
            PostMetric.workspace_id == ctx.workspace.id, PostMetric.published_on.between(start, end))
            .order_by(PostMetric.published_on))).scalars().all()
        rows = [[m.published_on.isoformat(), m.platform, m.post_label, m.post_url or "",
                 *[getattr(m, f) if getattr(m, f) is not None else "" for f in svc.METRIC_FIELDS], m.source]
                for m in metrics]
        return _download(svc.csv_bytes(["published_on", "platform", "post", "url", *svc.METRIC_FIELDS, "source"], rows),
                         name + ".csv", "text/csv")
    narrative = None
    if narrative_run_id:
        run, out = await _run_output(ctx, narrative_run_id, "creator.report_writer")
        from app.ai.agents.creator import PerformanceNarrative
        narrative = PerformanceNarrative.model_validate(out).render()
    ca = (await ctx.session.execute(select(ClientAccount.client_name).where(
        ClientAccount.workspace_id == ctx.workspace.id))).scalar_one_or_none()
    md = svc.report_markdown(ca or ctx.workspace.name, summary, narrative)
    if format == "md":
        return _download(md.encode(), name + ".md", "text/markdown")
    return _download(svc.markdown_to_html(md, f"Report: {ca or ctx.workspace.name}").encode(), name + ".html",
                     "text/html")


# ====================================================================== library export
@router.get("/library/export")
async def export_library(format: str = Query(pattern="^(csv|md)$"), status: str | None = None,
                         ctx: WsCtx = Depends(creator_ctx)):
    stmt = select(Asset, AssetVersion).join(AssetVersion, and_(AssetVersion.asset_id == Asset.id,
                                                               AssetVersion.version == Asset.current_version)).where(
        Asset.workspace_id == ctx.workspace.id, Asset.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Asset.status == status)
    rows = (await ctx.session.execute(stmt.order_by(Asset.created_at))).all()
    name = f"{_safe_name(ctx.workspace.name)}-content"
    if format == "csv":
        return _download(svc.csv_bytes(["title", "type", "status", "version", "tags", "updated_at", "text"],
                                       [[a.title, a.type, a.status, a.current_version, " ".join(a.tags),
                                         a.updated_at.isoformat(), v.body_text] for a, v in rows]),
                         name + ".csv", "text/csv")
    md = [f"# Content library: {ctx.workspace.name}", ""]
    for a, v in rows:
        md += [f"## {a.title}", f"_{a.type} · {a.status.replace('_', ' ')} · version {a.current_version}_", "",
               v.body_text or "(no text)", ""]
    return _download("\n".join(md).encode(), name + ".md", "text/markdown")
