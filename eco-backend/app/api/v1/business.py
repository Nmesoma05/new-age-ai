"""Business Marketing division API.

Two routers:
  - `accounts`: onboarding, the list of businesses, categories and the capability matrix (account level)
  - `router`:   everything inside one business workspace (/v1/workspaces/{id}/business/...)

Nothing here launches ads, spends money, sends messages or pulls figures from ad accounts, CRMs or analytics.
External actions can only be *requested*: they become pending actions that an admin must approve, and with no
integration connected, approval says so honestly (see /assistant/actions/{id}/approve -> no_executor).
Results are recorded by people (by hand or CSV) and every row keeps its `source`.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from sqlalchemy import delete, func, select

from app.ai import orchestrator
from app.ai.agents.specs import REGISTRY
from app.ai.context import AgentContext
from app.ai.orchestrator import RunRequest
from app.ai.providers import get_embedder, get_llm_provider
from app.ai.providers.base import LLMProvider
from app.ai.research import get_research_backend
from app.api.v1.workspaces import create_workspace_row
from app.core.deps import Principal, WsCtx, get_principal, ws_ctx
from app.core.errors import AppError, forbidden, not_found
from app.models import (
    AgentRun,
    Asset,
    AssetVersion,
    BusinessProfile,
    Campaign,
    Conversation,
    MarketingResult,
    Organisation,
    OrgMember,
    PendingAction,
    ProductAccess,
    Project,
    Workspace,
)
from app.schemas.business import (
    ApplyPositioningIn,
    ApprovalRequestIn,
    BizCampaignIn,
    BizCampaignOut,
    BizCampaignPatch,
    BizGenerateIn,
    BizOnboardingIn,
    BusinessSummary,
    IntelligenceIn,
    NewBusinessIn,
    ResultIn,
    ResultOut,
    SaveRunIn,
)
from app.schemas.common import (
    AssetOut,
    BusinessProfileOut,
    ExchangeOut,
    MessageOut,
    PendingActionOut,
    RunSummaryOut,
)
from app.services import audit, billing
from app.services import business as svc
from app.services.creator import csv_bytes, markdown_to_html
from app.services.storage import content_disposition

accounts = APIRouter(prefix="/v1/business", tags=["business"])
router = APIRouter(prefix="/v1/workspaces/{workspace_id}/business", tags=["business"])

TOOLS = {  # tool -> (agent, asset type it saves as, label, default brief)
    "intelligence": ("business.profile_builder", "intelligence_profile", "Marketing Intelligence Profile",
                     "Build my Marketing Intelligence Profile from my business profile."),
    "positioning": ("business.positioning_strategist", "positioning", "Positioning & messaging",
                    "Define my positioning, brand personality and key messages."),
    "market": ("business.market_analyst", "research", "Market & customer research",
               "Analyse my market and customers and tell me what to validate."),
    "competitors": ("business.market_analyst", "competitor_analysis", "Competitor analysis",
                    "Compare my business with my competitors and find where I can win."),
    "plan": ("business.marketing_planner", "marketing_plan", "Marketing plan", "Create a practical marketing plan."),
    "content": ("business.aida_strategist", "content_plan", "Content & social strategy (AIDA)",
                "Plan my social media content using AIDA."),
    "ads": ("business.ads_planner", "ad_plan", "Advertising plan", "Plan a paid advertising campaign."),
    "acquisition": ("business.growth_strategist", "growth_plan", "Lead generation & acquisition",
                    "Build a lead generation and customer acquisition plan."),
    "retention": ("business.growth_strategist", "growth_plan", "Customer retention",
                  "Give me practical ideas to keep customers coming back."),
    "report": ("business.performance_analyst", "report", "Performance report",
               "Analyse my recorded marketing results."),
}
TOOL_TITLE_PREFIX = "Studio · "
_OUTPUT_TAIL = ("uncertainties", "warnings", "memory_candidates")


# ====================================================================== helpers
async def business_ctx(ctx: WsCtx = Depends(ws_ctx)) -> WsCtx:
    if ctx.workspace.product != "business":
        raise AppError(409, "wrong_product", "Not a Business workspace",
                       "These tools are for Business Marketing workspaces.")
    return ctx


async def _profile(ctx: WsCtx, required: bool = True) -> BusinessProfile | None:
    p = (await ctx.session.execute(select(BusinessProfile).where(
        BusinessProfile.workspace_id == ctx.workspace.id))).scalar_one_or_none()
    if p is None and required:
        raise AppError(409, "no_profile", "Add your business profile first", "Save the business profile first.")
    return p


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


def _strip_tail(out: dict) -> dict:
    return {k: v for k, v in out.items() if k not in _OUTPUT_TAIL}


async def _finished_run(ctx: WsCtx, run_id: uuid.UUID, agents: tuple[str, ...] | None = None) -> AgentRun:
    run = await ctx.session.get(AgentRun, run_id)
    if run is None or run.workspace_id != ctx.workspace.id:
        raise not_found("run")
    if run.status != "succeeded" or not run.output or (agents and run.agent not in agents):
        raise AppError(409, "wrong_run", "Can't use that result", "That result isn't a finished output of the right kind.")
    return run


def _tool_of(run: AgentRun) -> str:
    """Which tool produced a run. Runs are immutable, so this is read back from the output itself."""
    if run.agent == "business.market_analyst":
        return "competitors" if run.output.get("focus") == "competitors" else "market"
    if run.agent == "business.growth_strategist":
        return run.output.get("focus", "acquisition")
    return next(t for t, v in TOOLS.items() if v[0] == run.agent)


def _render(run: AgentRun) -> str:
    return REGISTRY[run.agent].output_model.model_validate(run.output).render()


# ====================================================================== onboarding & businesses
async def _business_rows(p: Principal) -> list[BusinessSummary]:
    rows = (await p.session.execute(
        select(Workspace, Organisation, BusinessProfile, func.app.ws_role(Workspace.id))
        .join(Organisation, Organisation.id == Workspace.org_id)
        .outerjoin(BusinessProfile, BusinessProfile.workspace_id == Workspace.id)
        .where(Workspace.product == "business", Workspace.deleted_at.is_(None))
        .order_by(Workspace.created_at))).all()
    return [BusinessSummary(workspace_id=ws.id, workspace_name=ws.name, org_id=org.id, org_name=org.name,
                            org_kind=org.kind, role=role, business_name=bp.business_name if bp else None,
                            category=bp.category if bp else None, stage=bp.stage if bp else None,
                            location=bp.location if bp else None, profile_complete=svc.completeness(bp),
                            has_intelligence=bool(bp and bp.intelligence), created_at=ws.created_at)
            for ws, org, bp, role in rows if role in ("admin", "editor", "viewer")]


async def _enable(p: Principal, org: Organisation, request: Request) -> None:
    if await p.session.get(ProductAccess, (org.id, "business")) is None:
        p.session.add(ProductAccess(org_id=org.id, product="business", status="active"))
        await p.session.flush()
        await audit.record(p.session, "org.product_enrolled", actor_id=p.id, org_id=org.id, target_type="product",
                           target_id="business", request=request)


async def _create_business(p: Principal, org: Organisation, profile, request: Request) -> Workspace:
    ws = await create_workspace_row(p, org, profile.business_name[:120], "business", request)
    p.session.add(BusinessProfile(workspace_id=ws.id, org_id=org.id, **profile.model_dump(mode="json")))
    await p.session.flush()
    await audit.record(p.session, "profile.business_saved", actor_id=p.id, org_id=org.id, workspace_id=ws.id,
                       target_type="workspace", target_id=ws.id, request=request)
    return ws


@accounts.get("/onboarding")
async def onboarding_state(p: Principal = Depends(get_principal)):
    orgs = (await p.session.execute(
        select(Organisation, OrgMember.role).join(OrgMember, OrgMember.org_id == Organisation.id)
        .where(OrgMember.user_id == p.id, Organisation.deleted_at.is_(None)).order_by(Organisation.created_at))).all()
    org_list = []
    for org, role in orgs:
        ent = await billing.entitlements(p.session, org.id)
        org_list.append({"id": str(org.id), "name": org.name, "kind": org.kind, "role": role, "plan": ent.plan.code,
                         "max_workspaces": ent.plan.max_workspaces,
                         "business_enabled": await p.session.get(ProductAccess, (org.id, "business")) is not None})
    rows = await _business_rows(p)
    return {"has_business_workspace": bool(rows), "orgs": org_list,
            "businesses": [r.model_dump(mode="json") for r in rows],
            "next_step": "done" if rows else "create_first_business"}


@accounts.post("/onboarding", status_code=201)
async def complete_onboarding(body: BizOnboardingIn, request: Request, p: Principal = Depends(get_principal)):
    """One step: picks the personal org (solo) or creates a team org, turns the product on, and creates the first
    business workspace with its profile. The Intelligence Profile is generated next, on request."""
    if body.mode == "solo":
        org = (await p.session.execute(select(Organisation).where(
            Organisation.owner_user_id == p.id, Organisation.kind == "personal",
            Organisation.deleted_at.is_(None)))).scalar_one()
    else:
        org = Organisation(name=body.team_name, kind="team", owner_user_id=p.id)
        p.session.add(org)
        await p.session.flush()
        p.session.add(OrgMember(org_id=org.id, user_id=p.id, role="owner"))
        await p.session.flush()
        await audit.record(p.session, "org.created", actor_id=p.id, org_id=org.id, target_type="org",
                           target_id=org.id, request=request)
    await _enable(p, org, request)
    ws = await _create_business(p, org, body.profile, request)
    return {"org_id": str(org.id), "workspace_id": str(ws.id)}


@accounts.get("/businesses", response_model=list[BusinessSummary])
async def list_businesses(p: Principal = Depends(get_principal)):
    return await _business_rows(p)


@accounts.post("/businesses", status_code=201)
async def add_business(body: NewBusinessIn, request: Request, p: Principal = Depends(get_principal)):
    org = await p.session.get(Organisation, body.org_id)
    role = (await p.session.execute(select(OrgMember.role).where(OrgMember.org_id == body.org_id,
                                                                 OrgMember.user_id == p.id))).scalar_one_or_none()
    if org is None or role is None or org.deleted_at is not None:
        raise not_found("org")
    if role not in ("owner", "admin"):
        raise forbidden("Only organisation owners and admins can add businesses.")
    await _enable(p, org, request)
    ws = await _create_business(p, org, body.profile, request)
    return {"org_id": str(org.id), "workspace_id": str(ws.id)}


@accounts.get("/categories")
async def categories():
    """Category playbooks used to tailor advice; general guidance only, the business's own facts win."""
    return {"categories": [{"key": k, **v} for k, v in svc.CATEGORIES.items()],
            "stages": [{"key": k, **v} for k, v in svc.STAGES.items()],
            "channels": [{"key": k, "label": v} for k, v in svc.CHANNELS.items()]}


@accounts.get("/capabilities")
async def capabilities():
    return {"features": svc.CAPABILITIES}


# ====================================================================== dashboard
@router.get("/overview")
async def overview(ctx: WsCtx = Depends(business_ctx)):
    s, ws = ctx.session, ctx.workspace
    p = await _profile(ctx, required=False)
    types = dict((await s.execute(select(Asset.type, func.count()).where(
        Asset.workspace_id == ws.id, Asset.deleted_at.is_(None)).group_by(Asset.type))).all())
    recent = (await s.execute(select(Asset).where(Asset.workspace_id == ws.id, Asset.deleted_at.is_(None))
                              .order_by(Asset.updated_at.desc()).limit(6))).scalars().all()
    projects = (await s.execute(select(Project).where(Project.workspace_id == ws.id, Project.status == "active")
                                .order_by(Project.created_at.desc()).limit(8))).scalars().all()
    campaigns = (await s.execute(select(Campaign).where(Campaign.workspace_id == ws.id,
                                                        Campaign.status.in_(("draft", "active")))
                                 .order_by(Campaign.created_at.desc()).limit(5))).scalars().all()
    pending = (await s.execute(select(func.count()).select_from(PendingAction).where(
        PendingAction.workspace_id == ws.id, PendingAction.status == "awaiting_approval"))).scalar_one()
    end = date.today()
    start = end - timedelta(days=29)
    rows = (await s.execute(select(MarketingResult).where(MarketingResult.workspace_id == ws.id,
                                                          MarketingResult.period_end >= start,
                                                          MarketingResult.period_start <= end))).scalars().all()
    any_results = (await s.execute(select(func.count()).select_from(MarketingResult).where(
        MarketingResult.workspace_id == ws.id))).scalar_one() > 0
    ent = await billing.entitlements(s, ws.org_id)
    used = None if ent.is_paid_active else await billing.free_used(s, ws.org_id)
    cat = svc.CATEGORIES.get(p.category if p else "other", svc.CATEGORIES["other"])
    return {
        "workspace": {"id": str(ws.id), "name": ws.name, "role": ctx.role},
        "business": None if p is None else {
            "name": p.business_name, "category": p.category, "category_label": cat["label"], "stage": p.stage,
            "stage_label": svc.STAGES[p.stage]["label"], "location": p.location, "currency": svc._cur(p) or None,
            "profile_complete": svc.completeness(p), "has_intelligence": bool(p.intelligence),
            "intelligence_updated_at": p.intelligence_updated_at.isoformat() if p.intelligence_updated_at else None,
            "summary": (p.intelligence or {}).get("summary"), "priorities": (p.intelligence or {}).get("priorities", [])},
        "next_steps": svc.next_steps(p, set(types), any_results),
        "saved": types,
        "recent": [AssetOut.model_validate(a).model_dump(mode="json") for a in recent],
        "projects": [{"id": str(x.id), "name": x.name} for x in projects],
        "campaigns": [BizCampaignOut.model_validate(c).model_dump(mode="json") for c in campaigns],
        "pending_approvals": pending,
        "results_30d": svc.summarise_results(start, end, list(rows), svc._cur(p) if p else None),
        "plan": {"code": ent.plan.code, "name": ent.plan.name, "ai_unlimited": ent.is_paid_active,
                 "free_used": used, "free_limit": ent.plan.free_monthly_limit,
                 "free_remaining": None if used is None else max(0, (ent.plan.free_monthly_limit or 0) - used)},
        "integrations": {"ads": "requires_integration", "messaging": "requires_integration",
                         "results_import": "requires_integration"},
    }


# ====================================================================== Marketing Intelligence Profile (editable)
@router.put("/intelligence", response_model=BusinessProfileOut)
async def edit_intelligence(body: IntelligenceIn, ctx: WsCtx = Depends(business_ctx)):
    await ctx.require("ws.write")
    p = await _profile(ctx)
    keep = {k: v for k, v in (p.intelligence or {}).items() if k == "source_run_id"}  # provenance survives edits
    p.intelligence = {**body.model_dump(mode="json"), **keep, "edited_by_user": True}
    p.intelligence_updated_at, p.version = datetime.now(UTC), p.version + 1
    await ctx.session.flush()
    await ctx.session.refresh(p)
    await _audit(ctx, "business.intelligence_edited", "business_profile", p.id)
    return p


# ====================================================================== AI tools
async def _results_for(ctx: WsCtx, start: date, end: date) -> list[MarketingResult]:
    return list((await ctx.session.execute(select(MarketingResult).where(
        MarketingResult.workspace_id == ctx.workspace.id, MarketingResult.period_end >= start,
        MarketingResult.period_start <= end).order_by(MarketingResult.period_start))).scalars().all())


def _tool_message(body: BizGenerateIn, p: BusinessProfile, results: str = "") -> str:
    """Business framing + the request + structured lines the agents' validators parse back (Focus, Plan length,
    Date range, Platforms), so the model is held to exactly what the owner asked for."""
    lines = [svc.business_context(p), "", "## The owner's request", body.brief.strip() or TOOLS[body.tool][3]]
    if body.tool in ("market", "competitors"):
        lines.append(f"Focus: {'competitors' if body.tool == 'competitors' else 'market'}")
    if body.tool == "competitors":
        lines.append("Competitors to compare: " + ", ".join(c["name"] for c in p.competitors if c.get("name")))
    if body.tool in ("acquisition", "retention"):
        lines.append(f"Focus: {body.tool}")
    if body.tool == "plan":
        lines.append(f"Plan length: {body.plan_months or 3} months")
    if body.tool == "content" and body.platforms:
        lines.append("Platforms: " + ", ".join(body.platforms))
    if body.start_date and body.end_date and body.tool in ("ads", "report"):
        lines.append(f"Date range: {body.start_date.isoformat()} to {body.end_date.isoformat()}")
    if results:
        lines += ["", results]
    return "\n".join(lines)


@router.post("/generate", response_model=ExchangeOut, status_code=201)
async def generate(body: BizGenerateIn, ctx: WsCtx = Depends(business_ctx),
                   provider: LLMProvider = Depends(get_llm_provider), embedder=Depends(get_embedder),
                   research=Depends(get_research_backend)):
    """Run one Business tool in its own conversation (so earlier outputs don't leak into a new request). The output
    is structured; saving, applying and approvals are separate, explicit steps."""
    await ctx.require("ws.ai.run")
    s = ctx.session
    p = await _profile(ctx)
    if body.tool == "competitors" and not any(c.get("name") for c in p.competitors):
        raise AppError(422, "no_competitors", "Add competitors first",
                       "Name at least one competitor in your profile so the analysis is about real businesses.")
    results = ""
    if body.tool == "report":
        rows = await _results_for(ctx, body.start_date, body.end_date)
        if not rows:
            raise AppError(422, "no_results", "No results recorded",
                           "Record some results for this period first. Nothing is fetched from ad accounts.")
        results = svc.results_text(svc.summarise_results(body.start_date, body.end_date, rows, svc._cur(p)))
    message = _tool_message(body, p, results)
    agent = TOOLS[body.tool][0]
    conv = Conversation(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, created_by=ctx.principal.id,
                        title=f"{TOOL_TITLE_PREFIX}{TOOLS[body.tool][2]}"[:200])
    s.add(conv)
    await s.flush()
    actx = AgentContext(session=s, user_id=ctx.principal.id, org_id=ctx.workspace.org_id,
                        workspace_id=ctx.workspace.id, workspace_name=ctx.workspace.name, product="business",
                        role=ctx.role, provider=provider, embedder=embedder, research=research,
                        conversation_id=conv.id, request=ctx.request)
    result = await orchestrator.run(actx, RunRequest(message=message, conversation=conv, agent=agent,
                                                     document_ids=body.document_ids))
    r = result.run
    return ExchangeOut(user_message=MessageOut.model_validate(result.user_message),
                       assistant_message=MessageOut.model_validate(result.assistant_message),
                       run=RunSummaryOut(id=r.id, agent=r.agent, status=r.status, output=result.output,
                                         warnings=r.warnings, uncertainties=r.uncertainties,
                                         injection_detected=bool(r.injection_flags),
                                         pending_actions=result.pending_actions, saved_asset_id=result.saved_asset_id,
                                         memory_saved=result.memory_saved))


@router.post("/runs/{run_id}/save", response_model=AssetOut, status_code=201)
async def save_run(run_id: uuid.UUID, body: SaveRunIn, ctx: WsCtx = Depends(business_ctx)):
    """Save a tool's output as an editable, versioned item, optionally inside a project."""
    await ctx.require("ws.write")
    run = await _finished_run(ctx, run_id, tuple({v[0] for v in TOOLS.values()}))
    tool = _tool_of(run)
    if body.project_id:
        await _get_in_ws(ctx, Project, body.project_id, "project")
    a = Asset(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, project_id=body.project_id,
              type=TOOLS[tool][1], title=body.title or f"{TOOLS[tool][2]} · {date.today().isoformat()}",
              tags=[tool], created_by=ctx.principal.id)
    ctx.session.add(a)
    await ctx.session.flush()
    ctx.session.add(AssetVersion(asset_id=a.id, workspace_id=a.workspace_id, org_id=a.org_id, version=1,
                                 body={"tool": tool, "run_id": str(run.id), "output": run.output},
                                 body_text=_render(run), source="ai", author_id=ctx.principal.id))
    await ctx.session.flush()
    await ctx.session.refresh(a)
    await _audit(ctx, "business.output_saved", "asset", a.id, tool=tool, run=str(run.id))
    return a


@router.post("/runs/{run_id}/apply-intelligence", response_model=BusinessProfileOut)
async def apply_intelligence(run_id: uuid.UUID, ctx: WsCtx = Depends(business_ctx)):
    """Make a generated Intelligence Profile the business's current one (it stays editable)."""
    await ctx.require("ws.write")
    run = await _finished_run(ctx, run_id, ("business.profile_builder",))
    p = await _profile(ctx)
    p.intelligence = {**_strip_tail(run.output), "source_run_id": str(run.id),
                      "uncertainties": run.output.get("uncertainties", [])}
    p.intelligence_updated_at, p.version = datetime.now(UTC), p.version + 1
    await ctx.session.flush()
    await ctx.session.refresh(p)
    await _audit(ctx, "business.intelligence_applied", "agent_run", run.id)
    return p


@router.post("/runs/{run_id}/apply-positioning")
async def apply_positioning(run_id: uuid.UUID, body: ApplyPositioningIn, ctx: WsCtx = Depends(business_ctx)):
    """Copy chosen parts of a positioning run into the profile's brand section. Nothing is applied automatically."""
    await ctx.require("ws.write")
    run = await _finished_run(ctx, run_id, ("business.positioning_strategist",))
    out, p = run.output, await _profile(ctx)
    parts = {"positioning": ("positioning_statement", "value_proposition", "elevator_pitch"),
             "messages": ("key_messages", "taglines"),
             "voice": ("brand_personality", "tone_guidance", "words_to_use", "words_to_avoid", "do_and_dont"),
             "visual": ("visual_direction",)}
    brand = dict(p.brand or {})
    for part in body.parts:
        brand.update({k: out[k] for k in parts[part]})
    p.brand, p.version = brand, p.version + 1
    await ctx.session.flush()
    await _audit(ctx, "business.positioning_applied", "agent_run", run.id, parts=body.parts)
    return {"applied": body.parts, "version": p.version, "brand": brand}


@router.post("/runs/{run_id}/create-campaign", response_model=BizCampaignOut, status_code=201)
async def campaign_from_run(run_id: uuid.UUID, ctx: WsCtx = Depends(business_ctx)):
    """Turn an advertising plan into a trackable campaign (status draft). Nothing is launched."""
    await ctx.require("ws.write")
    run = await _finished_run(ctx, run_id, ("business.ads_planner",))
    out = run.output
    c = Campaign(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, name=out["objective"][:160],
                 objective=out["objective"][:1000], start_date=date.fromisoformat(out["start_date"]),
                 end_date=date.fromisoformat(out["end_date"]),
                 channels=list(dict.fromkeys(pl["channel"] for pl in out["platforms"])),
                 budget_note="; ".join(pl["budget_note"] for pl in out["platforms"])[:1000],
                 plan={"kind": "ad_plan", **_strip_tail(out)}, source_run_id=run.id, created_by=ctx.principal.id)
    ctx.session.add(c)
    await ctx.session.flush()
    await ctx.session.refresh(c)
    await _audit(ctx, "campaign.created", "campaign", c.id, from_run=str(run.id))
    return c


# ====================================================================== approvals for external actions
@router.post("/approvals", response_model=PendingActionOut, status_code=201)
async def request_approval(body: ApprovalRequestIn, ctx: WsCtx = Depends(business_ctx)):
    """Ask for approval to spend money (e.g. launch an ad plan) or send a message to customers. This only records
    the request; it never launches, pays or sends. Approval needs a workspace admin (and an org owner/admin for
    money), and even then nothing runs until an integration exists."""
    await ctx.require("ws.write")
    tainted = False
    if body.run_id:
        run = await _finished_run(ctx, body.run_id)
        src = {"run_id": str(run.id), "tool": _tool_of(run) if run.agent in {v[0] for v in TOOLS.values()} else None}
        tainted = bool(run.tainted)
    else:
        a = await _get_in_ws(ctx, Asset, body.asset_id, "asset")
        src = {"asset_id": str(a.id), "asset_title": a.title}
    payload = {**src, "amount": str(body.amount) if body.amount is not None else None, "currency": body.currency,
               "channel": body.channel, "audience": body.audience, "notes": body.notes}
    pa = PendingAction(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, run_id=body.run_id,
                       kind=body.kind, title=body.title, payload=payload, from_untrusted=tainted,
                       requested_by=ctx.principal.id)
    ctx.session.add(pa)
    await ctx.session.flush()
    await ctx.session.refresh(pa)
    await _audit(ctx, "business.approval_requested", "pending_action", pa.id, kind=body.kind)
    return pa


# ====================================================================== saved work (project storage)
@router.get("/work", response_model=list[AssetOut])
async def list_work(project_id: uuid.UUID | None = None, type: str | None = None, unfiled: bool = False,
                    ctx: WsCtx = Depends(business_ctx)):
    stmt = select(Asset).where(Asset.workspace_id == ctx.workspace.id, Asset.deleted_at.is_(None))
    if project_id:
        stmt = stmt.where(Asset.project_id == project_id)
    elif unfiled:
        stmt = stmt.where(Asset.project_id.is_(None))
    if type:
        stmt = stmt.where(Asset.type == type)
    return (await ctx.session.execute(stmt.order_by(Asset.updated_at.desc()).limit(200))).scalars().all()


@router.patch("/work/{asset_id}/project", response_model=AssetOut)
async def move_work(asset_id: uuid.UUID, project_id: uuid.UUID | None = Query(default=None),
                    ctx: WsCtx = Depends(business_ctx)):
    await ctx.require("ws.write")
    a = await _get_in_ws(ctx, Asset, asset_id, "asset")
    if project_id:
        await _get_in_ws(ctx, Project, project_id, "project")
    a.project_id = project_id
    await ctx.session.flush()
    await ctx.session.refresh(a)
    return a


@router.get("/work/{asset_id}/export")
async def export_work(asset_id: uuid.UUID, format: str = Query(pattern="^(md|html)$"),
                      ctx: WsCtx = Depends(business_ctx)):
    a = await _get_in_ws(ctx, Asset, asset_id, "asset")
    v = (await ctx.session.execute(select(AssetVersion).where(AssetVersion.asset_id == a.id,
                                                              AssetVersion.version == a.current_version))).scalar_one()
    md = f"# {a.title}\n\n{v.body_text}\n"
    name = _safe_name(a.title)
    if format == "md":
        return _download(md.encode(), f"{name}.md", "text/markdown; charset=utf-8")
    return _download(markdown_to_html(md, a.title).encode(), f"{name}.html", "text/html; charset=utf-8")


# ====================================================================== campaigns
@router.get("/campaigns", response_model=list[BizCampaignOut])
async def list_campaigns(ctx: WsCtx = Depends(business_ctx)):
    return (await ctx.session.execute(select(Campaign).where(Campaign.workspace_id == ctx.workspace.id)
                                      .order_by(Campaign.created_at.desc()).limit(200))).scalars().all()


@router.post("/campaigns", response_model=BizCampaignOut, status_code=201)
async def create_campaign(body: BizCampaignIn, ctx: WsCtx = Depends(business_ctx)):
    await ctx.require("ws.write")
    c = Campaign(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, created_by=ctx.principal.id,
                 **body.model_dump())
    ctx.session.add(c)
    await ctx.session.flush()
    await ctx.session.refresh(c)
    await _audit(ctx, "campaign.created", "campaign", c.id)
    return c


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: uuid.UUID, ctx: WsCtx = Depends(business_ctx)):
    c = await _get_in_ws(ctx, Campaign, campaign_id, "campaign")
    rows = (await ctx.session.execute(select(MarketingResult).where(MarketingResult.campaign_id == c.id)
                                      .order_by(MarketingResult.period_start))).scalars().all()
    p = await _profile(ctx, required=False)
    start = min((r.period_start for r in rows), default=c.start_date or date.today())
    end = max((r.period_end for r in rows), default=c.end_date or date.today())
    return {"campaign": BizCampaignOut.model_validate(c).model_dump(mode="json"),
            "results": [ResultOut.model_validate(r).model_dump(mode="json") for r in rows],
            "summary": svc.summarise_results(start, end, list(rows), svc._cur(p) if p else None)}


@router.patch("/campaigns/{campaign_id}", response_model=BizCampaignOut)
async def update_campaign(campaign_id: uuid.UUID, body: BizCampaignPatch, ctx: WsCtx = Depends(business_ctx)):
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
async def delete_campaign(campaign_id: uuid.UUID, ctx: WsCtx = Depends(business_ctx)):
    await ctx.require("ws.write")
    c = await _get_in_ws(ctx, Campaign, campaign_id, "campaign")
    await ctx.session.delete(c)  # results keep existing, unlinked
    await _audit(ctx, "campaign.deleted", "campaign", c.id)
    return Response(status_code=204)


# ====================================================================== results & reports
def _range(start: date | None, end: date | None) -> tuple[date, date]:
    end = end or date.today()
    start = start or end - timedelta(days=29)
    if start > end or (end - start).days > 400:
        raise AppError(422, "bad_range", "Check the dates", "Pick a range of up to 400 days, start before end.")
    return start, end


@router.get("/results", response_model=list[ResultOut])
async def list_results(start: date | None = None, end: date | None = None, ctx: WsCtx = Depends(business_ctx)):
    start, end = _range(start, end)
    return await _results_for(ctx, start, end)


@router.post("/results", response_model=ResultOut, status_code=201)
async def add_result(body: ResultIn, ctx: WsCtx = Depends(business_ctx)):
    await ctx.require("ws.write")
    p = await _profile(ctx, required=False)
    cur = body.currency or (svc._cur(p) if p else None)
    if not cur:
        raise AppError(422, "currency_required", "Which currency?", "Add a currency (e.g. NGN) or set one in your budget.")
    if body.campaign_id:
        await _get_in_ws(ctx, Campaign, body.campaign_id, "campaign")
    r = MarketingResult(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, source="manual",
                        created_by=ctx.principal.id, **{**body.model_dump(exclude={"currency"}), "currency": cur})
    ctx.session.add(r)
    await ctx.session.flush()
    await ctx.session.refresh(r)
    return r


@router.delete("/results/{result_id}", status_code=204)
async def delete_result(result_id: uuid.UUID, ctx: WsCtx = Depends(business_ctx)):
    await ctx.require("ws.write")
    r = await _get_in_ws(ctx, MarketingResult, result_id, "result")
    await ctx.session.execute(delete(MarketingResult).where(MarketingResult.id == r.id))
    return Response(status_code=204)


@router.post("/results/import", status_code=201)
async def import_results(file: UploadFile = File(...), currency: str | None = Form(default=None),
                         campaign_id: uuid.UUID | None = Form(default=None), ctx: WsCtx = Depends(business_ctx)):
    """CSV with columns channel, period_start[, period_end, currency, spend, impressions, clicks, leads, customers,
    revenue]. All rows are checked first; nothing is saved if any row is wrong."""
    await ctx.require("ws.write")
    data = await file.read(2_000_001)
    if len(data) > 2_000_000:
        raise AppError(413, "file_too_large", "File too large", "Keep CSV files under 2 MB.")
    if currency and (len(currency) != 3 or not currency.isalpha() or not currency.isupper()):
        raise AppError(422, "bad_currency", "Check the currency", "Use a 3-letter code like NGN.")
    if campaign_id:
        await _get_in_ws(ctx, Campaign, campaign_id, "campaign")
    p = await _profile(ctx, required=False)
    rows, errors = svc.parse_results_csv(data, currency or (svc._cur(p) if p else None))
    if errors:
        raise AppError(422, "csv_invalid", "Some rows need fixing", f"{len(errors)} problem(s); nothing was imported.",
                       extra={"rows": errors[:50]})
    if not rows:
        raise AppError(422, "csv_empty", "No rows found", "The file has a header but no data rows.")
    for r in rows:
        ctx.session.add(MarketingResult(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, source="csv_import",
                                        campaign_id=campaign_id, created_by=ctx.principal.id, **r))
    await ctx.session.flush()
    await _audit(ctx, "business.results_imported", "workspace", ctx.workspace.id, rows=len(rows))
    return {"imported": len(rows)}


@router.get("/report")
async def report(start: date | None = None, end: date | None = None, ctx: WsCtx = Depends(business_ctx)):
    start, end = _range(start, end)
    p = await _profile(ctx, required=False)
    return svc.summarise_results(start, end, await _results_for(ctx, start, end), svc._cur(p) if p else None)


@router.get("/report/export")
async def export_report(start: date | None = None, end: date | None = None,
                        format: str = Query(pattern="^(csv|md|html)$"), run_id: uuid.UUID | None = None,
                        ctx: WsCtx = Depends(business_ctx)):
    """Export the results report. `run_id` (a performance analysis) adds the AI-written analysis."""
    start, end = _range(start, end)
    p = await _profile(ctx, required=False)
    rows = await _results_for(ctx, start, end)
    name = p.business_name if p else ctx.workspace.name
    fname = f"{_safe_name(name)}-results-{start}-{end}"
    if format == "csv":
        header = ["channel", "period_start", "period_end", "currency", "spend", "impressions", "clicks", "leads",
                  "customers", "revenue", "source", "notes"]
        data = [[r.channel, r.period_start, r.period_end, r.currency, r.spend, r.impressions, r.clicks, r.leads,
                 r.customers, r.revenue, r.source, r.notes] for r in rows]
        return _download(csv_bytes(header, data), f"{fname}.csv", "text/csv; charset=utf-8")
    narrative = None
    if run_id:
        narrative = _render(await _finished_run(ctx, run_id, ("business.performance_analyst",)))
    md = svc.results_markdown(name, svc.summarise_results(start, end, rows, svc._cur(p) if p else None), narrative)
    if format == "md":
        return _download(md.encode(), f"{fname}.md", "text/markdown; charset=utf-8")
    return _download(markdown_to_html(md, f"Marketing results: {name}").encode(), f"{fname}.html",
                     "text/html; charset=utf-8")
