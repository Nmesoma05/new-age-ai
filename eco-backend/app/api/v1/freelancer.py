"""Freelancer Growth division API.

  - `accounts` (/v1/freelancer): onboarding, reference data (countries, currencies, conventions, resource directory),
    capabilities, rate-floor calculator
  - `router` (/v1/workspaces/{id}/freelancer): dashboard, AI tools, saved work, opportunities, applications,
    mock interviews

The freelancer workspace always lives in the user's personal organisation (enforced by create_workspace_row), so
teams never see a person's career data. Nothing is submitted, sent or posted from here, and opportunities are the
user's own entries: external, unverified until the user checks them at the source.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select

from app.ai import orchestrator
from app.ai.agents.specs import REGISTRY
from app.ai.context import AgentContext
from app.ai.orchestrator import RunRequest
from app.ai.providers import get_embedder, get_llm_provider
from app.ai.providers.base import LLMProvider
from app.ai.research import get_research_backend
from app.api.v1.business import _download, _safe_name, _strip_tail
from app.api.v1.workspaces import create_workspace_row
from app.core.deps import Principal, WsCtx, get_principal, ws_ctx
from app.core.errors import AppError, not_found
from app.models import (
    AgentRun,
    Application,
    Asset,
    AssetVersion,
    Conversation,
    InterviewSession,
    Opportunity,
    Organisation,
    ProductAccess,
    ProfessionalProfile,
    Project,
    Workspace,
)
from app.schemas.common import (
    AssetOut,
    ExchangeOut,
    MessageOut,
    ProfessionalProfileOut,
    RunSummaryOut,
)
from app.schemas.freelancer import (
    AnswerIn,
    ApplicationIn,
    ApplicationOut,
    ApplicationPatch,
    AssessmentIn,
    FlGenerateIn,
    FlOnboardingIn,
    InterviewIn,
    InterviewOut,
    OpportunityIn,
    OpportunityOut,
    OpportunityPatch,
    RateFloorIn,
    SaveRunIn,
    VerifyIn,
)
from app.services import audit, billing
from app.services import freelancer as svc
from app.services.creator import markdown_to_html

accounts = APIRouter(prefix="/v1/freelancer", tags=["freelancer"])
router = APIRouter(prefix="/v1/workspaces/{workspace_id}/freelancer", tags=["freelancer"])

TOOLS = {  # tool -> (agent, label, default brief)
    "assessment": ("freelancer.skills_assessor", "Skills assessment", "Assess my skills, strengths and gaps."),
    "cv": ("freelancer.cv_writer", "CV / resume", "Build my CV."),
    "proposal": ("freelancer.proposal_writer", "Proposal / cover letter", "Write my application."),
    "interview": ("freelancer.interview_coach", "Interview prep", "Prepare me for this interview."),
    "portfolio": ("freelancer.portfolio_builder", "Case study", "Write a case study from my best project."),
    "brand": ("freelancer.brand_writer", "Personal brand", "Write my bios and a few posts."),
    "outreach": ("freelancer.outreach_planner", "Client outreach", "Help me find and approach clients."),
    "pricing": ("freelancer.pricing_advisor", "Services & pricing", "Package and price my services."),
    "learning": ("freelancer.learning_planner", "Learning plan", "Make me a learning plan."),
    "opportunity": ("freelancer.opportunity_analyst", "Opportunity check", "Check this opportunity for me."),
}
SAVE_TYPE = {"freelancer.skills_assessor": "skills_assessment", "freelancer.cv_writer": "cv",
             "freelancer.interview_coach": "interview_prep", "freelancer.portfolio_builder": "case_study",
             "freelancer.brand_writer": "brand_content", "freelancer.outreach_planner": "outreach_plan",
             "freelancer.pricing_advisor": "service_package", "freelancer.learning_planner": "learning_plan",
             "freelancer.opportunity_analyst": "opportunity_analysis"}
ACTIVE_APPS = ("preparing", "applied", "interviewing", "offer")


# ====================================================================== helpers
async def fl_ctx(ctx: WsCtx = Depends(ws_ctx)) -> WsCtx:
    if ctx.workspace.product != "freelancer":
        raise AppError(409, "wrong_product", "Not a Freelancer workspace", "These tools are for Freelancer Growth.")
    return ctx


async def _profile(ctx: WsCtx, required: bool = True) -> ProfessionalProfile | None:
    p = (await ctx.session.execute(select(ProfessionalProfile).where(
        ProfessionalProfile.workspace_id == ctx.workspace.id))).scalar_one_or_none()
    if p is None and required:
        raise AppError(409, "no_profile", "Add your profile first", "Fill in your professional profile first.")
    return p


async def _get(ctx: WsCtx, model, obj_id: uuid.UUID, what: str):
    obj = await ctx.session.get(model, obj_id)
    if obj is None or obj.workspace_id != ctx.workspace.id or getattr(obj, "deleted_at", None) is not None:
        raise not_found(what)
    return obj


async def _audit(ctx: WsCtx, action: str, target_type: str, target_id, **meta) -> None:
    await audit.record(ctx.session, action, actor_id=ctx.principal.id, org_id=ctx.workspace.org_id,
                       workspace_id=ctx.workspace.id, target_type=target_type, target_id=target_id,
                       metadata=meta or None, request=ctx.request)


async def _finished_run(ctx: WsCtx, run_id: uuid.UUID, agents: tuple[str, ...]) -> AgentRun:
    run = await ctx.session.get(AgentRun, run_id)
    if run is None or run.workspace_id != ctx.workspace.id:
        raise not_found("run")
    if run.status != "succeeded" or not run.output or run.agent not in agents:
        raise AppError(409, "wrong_run", "Can't use that result", "That result isn't a finished output of the right kind.")
    return run


def _render(run: AgentRun) -> str:
    return REGISTRY[run.agent].output_model.model_validate(run.output).render()


def _opp_checks(o: Opportunity, p: ProfessionalProfile | None) -> dict:
    """Deterministic checks shown with every opportunity: eligibility from what the listing states, time-zone
    overlap for today's date, and scam warning signs. Expired-by-deadline is computed too."""
    elig = svc.eligibility(o.remote_type, o.eligible_countries, o.excluded_countries, p.country if p else None)
    overlap = svc.overlap_hours(p.timezone, o.timezone_requirement) if p and p.timezone else None
    return {"eligibility": elig.as_dict(), "timezone": overlap,
            "risk_signals": svc.risk_signals(f"{o.title}\n{o.description}"),
            "deadline_passed": bool(o.deadline and o.deadline < date.today()),
            "verified": o.status == "verified",
            "pay_note": "Shown in the listing's currency. Any conversion shown is an indicative daily rate." if o.pay_currency else None}


def _opp_out(o: Opportunity, p) -> dict:
    return {**OpportunityOut.model_validate(o).model_dump(mode="json"), "checks": _opp_checks(o, p)}


async def _expire(ctx: WsCtx) -> None:
    """Listings past their deadline stop counting as open (they're kept, marked expired)."""
    rows = (await ctx.session.execute(select(Opportunity).where(
        Opportunity.workspace_id == ctx.workspace.id, Opportunity.status.in_(("unverified", "verified")),
        Opportunity.deadline < date.today()))).scalars().all()
    for o in rows:
        o.status = "expired"
    if rows:
        await ctx.session.flush()


# ====================================================================== account level
@accounts.get("/reference")
async def reference():
    return {"stages": [{"key": k, **v} for k, v in svc.STAGES.items()],
            "work_modes": [{"key": k, "label": v} for k, v in svc.WORK_MODES.items()],
            "countries": [{"code": k, **v} for k, v in sorted(svc.COUNTRIES.items(), key=lambda x: x[1]["name"])],
            "currencies": svc.CURRENCIES,
            "conventions": [{"key": k, **v} for k, v in svc.CONVENTIONS.items()], "conventions_note": svc.CONVENTIONS_NOTE,
            "resources": {"checked_on": svc.CHECKED_ON, "categories": svc.RESOURCE_CATEGORIES, "items": svc.RESOURCES,
                          "note": "Checked on the date shown. Availability, fees and supported countries change: "
                                  "confirm for your country before relying on any of these. Not affiliated."}}


@accounts.get("/capabilities")
async def capabilities():
    return {"features": svc.CAPABILITIES}


@accounts.post("/rate-floor")
async def rate_floor(body: RateFloorIn):
    return svc.rate_floor(**body.model_dump())


async def _personal(p: Principal) -> Organisation:
    return (await p.session.execute(select(Organisation).where(
        Organisation.owner_user_id == p.id, Organisation.kind == "personal",
        Organisation.deleted_at.is_(None)))).scalar_one()


async def _my_ws(p: Principal) -> Workspace | None:
    org = await _personal(p)
    return (await p.session.execute(select(Workspace).where(
        Workspace.org_id == org.id, Workspace.product == "freelancer", Workspace.deleted_at.is_(None))
        .order_by(Workspace.created_at))).scalars().first()


@accounts.get("/onboarding")
async def onboarding_state(p: Principal = Depends(get_principal)):
    ws = await _my_ws(p)
    org = await _personal(p)
    ent = await billing.entitlements(p.session, org.id)
    used = (await p.session.execute(select(func.count()).select_from(Workspace).where(
        Workspace.org_id == org.id, Workspace.deleted_at.is_(None)))).scalar_one()
    return {"workspace_id": str(ws.id) if ws else None, "next_step": "done" if ws else "create_profile",
            "plan": ent.plan.code, "can_create": ws is None and used < ent.plan.max_workspaces,
            "workspaces_used": used, "max_workspaces": ent.plan.max_workspaces}


@accounts.post("/onboarding", status_code=201)
async def complete_onboarding(body: FlOnboardingIn, request: Request, p: Principal = Depends(get_principal)):
    """Creates the one Freelancer workspace in the personal organisation and saves the professional profile."""
    if await _my_ws(p):
        raise AppError(409, "already_set_up", "Already set up", "You already have a Freelancer workspace.")
    org = await _personal(p)
    if await p.session.get(ProductAccess, (org.id, "freelancer")) is None:
        p.session.add(ProductAccess(org_id=org.id, product="freelancer", status="active"))
        await p.session.flush()
        await audit.record(p.session, "org.product_enrolled", actor_id=p.id, org_id=org.id, target_type="product",
                           target_id="freelancer", request=request)
    ws = await create_workspace_row(p, org, "My career", "freelancer", request)
    p.session.add(ProfessionalProfile(workspace_id=ws.id, org_id=org.id, user_id=p.id, **body.profile.to_row()))
    await p.session.flush()
    await audit.record(p.session, "profile.professional_saved", actor_id=p.id, org_id=org.id, workspace_id=ws.id,
                       target_type="workspace", target_id=ws.id, request=request)
    return {"workspace_id": str(ws.id)}


# ====================================================================== dashboard
@router.get("/overview")
async def overview(ctx: WsCtx = Depends(fl_ctx)):
    s, ws = ctx.session, ctx.workspace
    await _expire(ctx)
    p = await _profile(ctx, required=False)
    saved = dict((await s.execute(select(Asset.type, func.count()).where(
        Asset.workspace_id == ws.id, Asset.deleted_at.is_(None)).group_by(Asset.type))).all())
    opp = dict((await s.execute(select(Opportunity.status, func.count()).where(
        Opportunity.workspace_id == ws.id).group_by(Opportunity.status))).all())
    apps = dict((await s.execute(select(Application.status, func.count()).where(
        Application.workspace_id == ws.id).group_by(Application.status))).all())
    due = (await s.execute(select(Application).where(
        Application.workspace_id == ws.id, Application.status.in_(ACTIVE_APPS),
        Application.next_step_due.is_not(None)).order_by(Application.next_step_due).limit(6))).scalars().all()
    recent = (await s.execute(select(Asset).where(Asset.workspace_id == ws.id, Asset.deleted_at.is_(None))
                              .order_by(Asset.updated_at.desc()).limit(6))).scalars().all()
    today = date.today()
    counts = {"opportunities": sum(opp.values()), "unverified": opp.get("unverified", 0),
              "interviewing": apps.get("interviewing", 0),
              "follow_ups_due": sum(1 for a in due if a.next_step_due <= today)}
    ent = await billing.entitlements(s, ws.org_id)
    used = None if ent.is_paid_active else await billing.free_used(s, ws.org_id)
    c = svc.COUNTRIES.get(p.country or "") if p else None
    return {
        "profile": None if p is None else {
            "full_name": p.full_name, "headline": p.headline, "career_stage": p.career_stage,
            "stage_label": svc.STAGES[p.career_stage]["label"], "country": p.country, "country_name": c["name"] if c else None,
            "city": p.city, "timezone": p.timezone, "currency": p.currency, "completeness": svc.completeness(p),
            "missing": svc.missing_basics(p), "has_assessment": bool(p.assessment),
            "strengths": (p.assessment or {}).get("strengths", [])},
        "next_steps": svc.next_steps(p, set(saved), counts),
        "saved": saved, "opportunities": opp, "applications": apps, "counts": counts,
        "follow_ups": [{"id": str(a.id), "title": a.title, "organisation": a.organisation, "next_step": a.next_step,
                        "due": a.next_step_due.isoformat(), "overdue": a.next_step_due < today} for a in due],
        "recent": [AssetOut.model_validate(a).model_dump(mode="json") for a in recent],
        "plan": {"code": ent.plan.code, "name": ent.plan.name, "ai_unlimited": ent.is_paid_active, "free_used": used,
                 "free_limit": ent.plan.free_monthly_limit,
                 "free_remaining": None if used is None else max(0, (ent.plan.free_monthly_limit or 0) - used)},
    }


@router.put("/assessment", response_model=ProfessionalProfileOut)
async def edit_assessment(body: AssessmentIn, ctx: WsCtx = Depends(fl_ctx)):
    await ctx.require("ws.write")
    p = await _profile(ctx)
    keep = {k: v for k, v in (p.assessment or {}).items() if k == "source_run_id"}
    p.assessment = {**body.model_dump(mode="json"), **keep, "edited_by_user": True}
    p.assessment_updated_at, p.version = datetime.now(UTC), p.version + 1
    await ctx.session.flush()
    await ctx.session.refresh(p)
    await _audit(ctx, "freelancer.assessment_edited", "professional_profile", p.id)
    return p


# ====================================================================== AI tools
def _tool_message(body: FlGenerateIn, p: ProfessionalProfile, extra: list[str]) -> str:
    lines = [svc.professional_context(p), "", "## The user's request", body.brief.strip() or TOOLS[body.tool][2], *extra]
    return "\n".join(lines)


@router.post("/generate", response_model=ExchangeOut, status_code=201)
async def generate(body: FlGenerateIn, ctx: WsCtx = Depends(fl_ctx),
                   provider: LLMProvider = Depends(get_llm_provider), embedder=Depends(get_embedder),
                   research=Depends(get_research_backend)):
    """Run one tool in its own conversation. Pasted job posts and saved listings go to the model as untrusted
    external material, never as the user's own words, so they can't become 'experience'."""
    await ctx.require("ws.ai.run")
    s = ctx.session
    p = await _profile(ctx)
    extra: list[str] = []
    external: list[tuple[str, str]] = []
    if body.job_text.strip():
        external.append(("job_post", body.job_text))
    if body.application_id:
        app_row = await _get(ctx, Application, body.application_id, "application")
        extra.append(f"Application: {app_row.title} at {app_row.organisation or 'the organisation'}")
        if app_row.opportunity_id and not body.opportunity_id:
            body.opportunity_id = app_row.opportunity_id
    if body.opportunity_id:
        o = await _get(ctx, Opportunity, body.opportunity_id, "opportunity")
        chk = _opp_checks(o, p)
        external.append(("listing", f"{o.title}\n{o.organisation}\n{o.location_note}\n{o.description}"))
        extra += [f"Opportunity: {o.title} ({o.organisation or 'organisation not given'}), saved by the user, "
                  f"status {o.status}" + ("" if o.status == "verified" else " (NOT yet verified at the source)"),
                  f"Eligibility (computed): {chk['eligibility']['status']} ({'; '.join(chk['eligibility']['reasons'])})",
                  "Time-zone overlap (computed): " + (f"{chk['timezone']['overlap_hours']} hours; required window "
                                                      f"{chk['timezone']['required_window_local']}" if chk["timezone"] else "unknown"),
                  "Red flags (computed): " + (", ".join(r["signal"] for r in chk["risk_signals"]) or "none")]
        if o.pay_currency:
            extra.append(f"Pay stated by the listing: {o.pay_currency} {o.pay_min or '?'}–{o.pay_max or '?'} per "
                         f"{o.pay_period} (not converted)")
    if body.tool in ("cv", "interview", "proposal") and body.target_role:
        extra.append(f"Target role: {body.target_role}")
    if body.tool == "cv":
        conv = svc.CONVENTIONS[body.market]
        extra += [f"Target market: {body.market}",
                  f"Conventions ({conv['label']}, general; employer instructions come first): document {conv['document']}; "
                  f"length {conv['length']}; photo: {conv['photo']}; personal details: {conv['personal_details']}; "
                  f"format: {conv['format']}; {conv['notes']}"]
    if body.tool == "proposal":
        extra.append(f"Document type: {body.letter_type}")
    if body.tool == "interview":
        extra += [f"Role: {body.target_role or 'the role'}", f"Question count: {body.question_count}"]
    if body.tool == "brand" and body.platforms:
        extra.append("Platforms: " + ", ".join(body.platforms))
    if body.tool == "pricing":
        t, av = p.targets or {}, p.availability or {}
        if t.get("income_goal_monthly") and av.get("hours_per_week"):
            f = svc.rate_floor(t["income_goal_monthly"], av["hours_per_week"])
            cur = t.get("currency") or p.currency or ""
            extra.append(f"Rate floor: {cur} {f['hourly_floor']} per hour, {cur} {f['daily_floor']} per day (from "
                         f"your income goal of {cur} {t['income_goal_monthly']:g} a month at {av['hours_per_week']} "
                         f"hours/week, 60% billable)")
    if body.tool == "learning":
        extra += [f"Weeks: {body.weeks}",
                  f"Hours per week: {body.hours_per_week or (p.availability or {}).get('hours_per_week') or 5}",
                  "Resource directory (the only links you may use; checked " + svc.CHECKED_ON + "):",
                  *(f"- {r['name']}: {r['url']} ({r['category']})" for r in svc.RESOURCES)]
    agent = TOOLS[body.tool][0]
    conv = Conversation(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, created_by=ctx.principal.id,
                        title=f"Studio · {TOOLS[body.tool][1]}"[:200])
    s.add(conv)
    await s.flush()
    actx = AgentContext(session=s, user_id=ctx.principal.id, org_id=ctx.workspace.org_id, workspace_id=ctx.workspace.id,
                        workspace_name=ctx.workspace.name, product="freelancer", role=ctx.role, provider=provider,
                        embedder=embedder, research=research, conversation_id=conv.id, request=ctx.request)
    result = await orchestrator.run(actx, RunRequest(message=_tool_message(body, p, extra), conversation=conv,
                                                     agent=agent, document_ids=body.document_ids, external=external))
    r = result.run
    if body.tool == "opportunity" and r.status == "succeeded" and result.output:
        o.analysis = {**_strip_tail(result.output), "run_id": str(r.id), "at": datetime.now(UTC).isoformat()}
        await s.flush()
    return ExchangeOut(user_message=MessageOut.model_validate(result.user_message),
                       assistant_message=MessageOut.model_validate(result.assistant_message),
                       run=RunSummaryOut(id=r.id, agent=r.agent, status=r.status, output=result.output,
                                         warnings=r.warnings, uncertainties=r.uncertainties,
                                         injection_detected=bool(r.injection_flags),
                                         pending_actions=result.pending_actions, saved_asset_id=result.saved_asset_id,
                                         memory_saved=result.memory_saved))


@router.post("/runs/{run_id}/save", response_model=AssetOut, status_code=201)
async def save_run(run_id: uuid.UUID, body: SaveRunIn, ctx: WsCtx = Depends(fl_ctx)):
    await ctx.require("ws.write")
    run = await _finished_run(ctx, run_id, tuple(v[0] for v in TOOLS.values()))
    if run.agent == "freelancer.proposal_writer":
        atype = "cover_letter" if run.output.get("document_type") == "cover_letter" else "proposal"
    else:
        atype = SAVE_TYPE[run.agent]
    if body.project_id:
        await _get(ctx, Project, body.project_id, "project")
    label = next(v[1] for v in TOOLS.values() if v[0] == run.agent)
    a = Asset(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, project_id=body.project_id, type=atype,
              title=body.title or f"{label} · {date.today().isoformat()}", tags=[run.agent.split(".")[1]],
              created_by=ctx.principal.id)
    ctx.session.add(a)
    await ctx.session.flush()
    ctx.session.add(AssetVersion(asset_id=a.id, workspace_id=a.workspace_id, org_id=a.org_id, version=1,
                                 body={"agent": run.agent, "run_id": str(run.id), "output": run.output},
                                 body_text=_render(run), source="ai", author_id=ctx.principal.id))
    await ctx.session.flush()
    await ctx.session.refresh(a)
    await _audit(ctx, "freelancer.output_saved", "asset", a.id, agent=run.agent)
    return a


@router.post("/runs/{run_id}/apply-assessment", response_model=ProfessionalProfileOut)
async def apply_assessment(run_id: uuid.UUID, ctx: WsCtx = Depends(fl_ctx)):
    await ctx.require("ws.write")
    run = await _finished_run(ctx, run_id, ("freelancer.skills_assessor",))
    p = await _profile(ctx)
    p.assessment = {**_strip_tail(run.output), "source_run_id": str(run.id)}
    p.assessment_updated_at, p.version = datetime.now(UTC), p.version + 1
    await ctx.session.flush()
    await ctx.session.refresh(p)
    await _audit(ctx, "freelancer.assessment_applied", "agent_run", run.id)
    return p


# ====================================================================== saved work
@router.get("/work", response_model=list[AssetOut])
async def list_work(project_id: uuid.UUID | None = None, type: str | None = None, ctx: WsCtx = Depends(fl_ctx)):
    stmt = select(Asset).where(Asset.workspace_id == ctx.workspace.id, Asset.deleted_at.is_(None))
    if project_id:
        stmt = stmt.where(Asset.project_id == project_id)
    if type:
        stmt = stmt.where(Asset.type == type)
    return (await ctx.session.execute(stmt.order_by(Asset.updated_at.desc()).limit(200))).scalars().all()


@router.patch("/work/{asset_id}/project", response_model=AssetOut)
async def move_work(asset_id: uuid.UUID, project_id: uuid.UUID | None = Query(default=None), ctx: WsCtx = Depends(fl_ctx)):
    await ctx.require("ws.write")
    a = await _get(ctx, Asset, asset_id, "asset")
    if project_id:
        await _get(ctx, Project, project_id, "project")
    a.project_id = project_id
    await ctx.session.flush()
    await ctx.session.refresh(a)
    return a


@router.get("/work/{asset_id}/export")
async def export_work(asset_id: uuid.UUID, format: str = Query(pattern="^(md|html|txt)$"), ctx: WsCtx = Depends(fl_ctx)):
    a = await _get(ctx, Asset, asset_id, "asset")
    v = (await ctx.session.execute(select(AssetVersion).where(AssetVersion.asset_id == a.id,
                                                              AssetVersion.version == a.current_version))).scalar_one()
    md = f"# {a.title}\n\n{v.body_text}\n"
    name = _safe_name(a.title)
    if format == "md":
        return _download(md.encode(), f"{name}.md", "text/markdown; charset=utf-8")
    if format == "txt":  # plain text pastes cleanly into application forms
        import re
        plain = re.sub(r"[*_`#>]+", "", md)
        return _download(plain.encode(), f"{name}.txt", "text/plain; charset=utf-8")
    return _download(markdown_to_html(md, a.title).encode(), f"{name}.html", "text/html; charset=utf-8")


# ====================================================================== opportunities
@router.get("/opportunities")
async def list_opportunities(status: str | None = None, ctx: WsCtx = Depends(fl_ctx)):
    await _expire(ctx)
    p = await _profile(ctx, required=False)
    stmt = select(Opportunity).where(Opportunity.workspace_id == ctx.workspace.id)
    if status:
        stmt = stmt.where(Opportunity.status == status)
    rows = (await ctx.session.execute(stmt.order_by(Opportunity.created_at.desc()).limit(200))).scalars().all()
    return [_opp_out(o, p) for o in rows]


@router.post("/opportunities", status_code=201)
async def add_opportunity(body: OpportunityIn, ctx: WsCtx = Depends(fl_ctx)):
    """Save a listing the user found. It's unverified until they confirm it at the source."""
    await ctx.require("ws.write")
    data = body.model_dump(mode="json", exclude={"timezone_requirement"})
    o = Opportunity(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, created_by=ctx.principal.id,
                    source="pasted" if body.description else "manual",
                    timezone_requirement=body.timezone_requirement.model_dump() if body.timezone_requirement else {},
                    **{**data, "pay_min": body.pay_min, "pay_max": body.pay_max})
    ctx.session.add(o)
    await ctx.session.flush()
    await ctx.session.refresh(o)
    await _audit(ctx, "freelancer.opportunity_added", "opportunity", o.id)
    return _opp_out(o, await _profile(ctx, required=False))


@router.get("/opportunities/{opp_id}")
async def get_opportunity(opp_id: uuid.UUID, ctx: WsCtx = Depends(fl_ctx)):
    o = await _get(ctx, Opportunity, opp_id, "opportunity")
    return {**_opp_out(o, await _profile(ctx, required=False)), "analysis": o.analysis}


@router.patch("/opportunities/{opp_id}")
async def update_opportunity(opp_id: uuid.UUID, body: OpportunityPatch, ctx: WsCtx = Depends(fl_ctx)):
    await ctx.require("ws.write")
    o = await _get(ctx, Opportunity, opp_id, "opportunity")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(o, k, v)
    await ctx.session.flush()
    await ctx.session.refresh(o)
    return _opp_out(o, await _profile(ctx, required=False))


@router.post("/opportunities/{opp_id}/verify")
async def verify_opportunity(opp_id: uuid.UUID, body: VerifyIn, ctx: WsCtx = Depends(fl_ctx)):
    """The user confirms they checked the original posting: still open (verified) or closed. The app can't check
    for them: there is no job-board integration."""
    await ctx.require("ws.write")
    o = await _get(ctx, Opportunity, opp_id, "opportunity")
    if body.still_open and o.deadline and o.deadline < date.today():
        raise AppError(409, "deadline_passed", "Deadline has passed",
                       "Update the deadline first if the posting has been extended.")
    o.status = "verified" if body.still_open else "closed"
    o.verified_at, o.verified_by, o.verification_note = datetime.now(UTC), ctx.principal.id, body.note
    await ctx.session.flush()
    await ctx.session.refresh(o)
    await _audit(ctx, "freelancer.opportunity_verified", "opportunity", o.id, still_open=body.still_open)
    return _opp_out(o, await _profile(ctx, required=False))


@router.delete("/opportunities/{opp_id}", status_code=204)
async def delete_opportunity(opp_id: uuid.UUID, ctx: WsCtx = Depends(fl_ctx)):
    await ctx.require("ws.write")
    o = await _get(ctx, Opportunity, opp_id, "opportunity")
    await ctx.session.delete(o)
    return Response(status_code=204)


@router.post("/opportunities/{opp_id}/track", response_model=ApplicationOut, status_code=201)
async def track_opportunity(opp_id: uuid.UUID, ctx: WsCtx = Depends(fl_ctx)):
    """Start an application from a saved opportunity (status 'preparing')."""
    await ctx.require("ws.write")
    o = await _get(ctx, Opportunity, opp_id, "opportunity")
    return await _new_application(ctx, ApplicationIn(title=o.title, organisation=o.organisation, url=o.url,
                                                     opportunity_id=o.id))


# ====================================================================== applications
async def _check_links(ctx: WsCtx, cv: uuid.UUID | None, letter: uuid.UUID | None, opp: uuid.UUID | None) -> None:
    for aid, types in ((cv, ("cv",)), (letter, ("cover_letter", "proposal"))):
        if aid:
            a = await _get(ctx, Asset, aid, "asset")
            if a.type not in types:
                raise AppError(422, "wrong_asset_type", "Wrong document", f"That item isn't a {' or '.join(types)}.")
    if opp:
        await _get(ctx, Opportunity, opp, "opportunity")


async def _new_application(ctx: WsCtx, body: ApplicationIn) -> Application:
    await _check_links(ctx, body.cv_asset_id, body.letter_asset_id, body.opportunity_id)
    a = Application(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, created_by=ctx.principal.id,
                    history=[{"at": datetime.now(UTC).isoformat(), "status": body.status, "note": "Created"}],
                    **body.model_dump())
    ctx.session.add(a)
    await ctx.session.flush()
    await ctx.session.refresh(a)
    await _audit(ctx, "freelancer.application_created", "application", a.id)
    return a


@router.get("/applications", response_model=list[ApplicationOut])
async def list_applications(status: str | None = None, ctx: WsCtx = Depends(fl_ctx)):
    stmt = select(Application).where(Application.workspace_id == ctx.workspace.id)
    if status:
        stmt = stmt.where(Application.status == status)
    return (await ctx.session.execute(stmt.order_by(Application.updated_at.desc()).limit(300))).scalars().all()


@router.post("/applications", response_model=ApplicationOut, status_code=201)
async def create_application(body: ApplicationIn, ctx: WsCtx = Depends(fl_ctx)):
    await ctx.require("ws.write")
    return await _new_application(ctx, body)


@router.patch("/applications/{app_id}", response_model=ApplicationOut)
async def update_application(app_id: uuid.UUID, body: ApplicationPatch, ctx: WsCtx = Depends(fl_ctx)):
    """Status changes are recorded in the application's history. Marking 'applied' means the user applied
    themselves: nothing is submitted from here."""
    await ctx.require("ws.write")
    a = await _get(ctx, Application, app_id, "application")
    data = body.model_dump(exclude_unset=True)
    note = data.pop("status_note", "")
    await _check_links(ctx, data.get("cv_asset_id"), data.get("letter_asset_id"), None)
    new_status = data.get("status")
    if new_status and new_status != a.status:
        a.history = [*a.history, {"at": datetime.now(UTC).isoformat(), "status": new_status, "note": note}][-50:]
        if new_status == "applied" and not a.applied_on and "applied_on" not in data:
            a.applied_on = date.today()
    for k, v in data.items():
        setattr(a, k, v)
    await ctx.session.flush()
    await ctx.session.refresh(a)
    return a


@router.delete("/applications/{app_id}", status_code=204)
async def delete_application(app_id: uuid.UUID, ctx: WsCtx = Depends(fl_ctx)):
    await ctx.require("ws.write")
    a = await _get(ctx, Application, app_id, "application")
    await ctx.session.delete(a)
    return Response(status_code=204)


# ====================================================================== mock interviews
@router.get("/interviews", response_model=list[InterviewOut])
async def list_interviews(ctx: WsCtx = Depends(fl_ctx)):
    return (await ctx.session.execute(select(InterviewSession).where(InterviewSession.workspace_id == ctx.workspace.id)
                                      .order_by(InterviewSession.created_at.desc()).limit(50))).scalars().all()


@router.post("/interviews", response_model=InterviewOut, status_code=201)
async def start_interview(body: InterviewIn, ctx: WsCtx = Depends(fl_ctx)):
    """A practice session from an interview-prep run's questions, or the user's own questions."""
    await ctx.require("ws.write")
    if body.application_id:
        await _get(ctx, Application, body.application_id, "application")
    questions = [{"question": q, "type": "own", "why_asked": ""} for q in body.questions]
    if body.run_id:
        run = await _finished_run(ctx, body.run_id, ("freelancer.interview_coach",))
        questions = [{"question": q["question"], "type": q["type"], "why_asked": q["why_asked"]}
                     for q in run.output["questions"]] + questions
    sess = InterviewSession(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, created_by=ctx.principal.id,
                            application_id=body.application_id, role_title=body.role_title, questions=questions[:15],
                            source_run_id=body.run_id)
    ctx.session.add(sess)
    await ctx.session.flush()
    await ctx.session.refresh(sess)
    return sess


@router.get("/interviews/{sid}", response_model=InterviewOut)
async def get_interview(sid: uuid.UUID, ctx: WsCtx = Depends(fl_ctx)):
    return await _get(ctx, InterviewSession, sid, "interview")


@router.post("/interviews/{sid}/answers", status_code=201)
async def answer_question(sid: uuid.UUID, body: AnswerIn, ctx: WsCtx = Depends(fl_ctx),
                          provider: LLMProvider = Depends(get_llm_provider), embedder=Depends(get_embedder),
                          research=Depends(get_research_backend)):
    """Type an answer; the answer coach scores it and shows a stronger version without inventing facts."""
    await ctx.require("ws.ai.run")
    sess = await _get(ctx, InterviewSession, sid, "interview")
    if sess.status != "active":
        raise AppError(409, "session_completed", "Session finished", "Start a new practice session.")
    if body.index >= len(sess.questions):
        raise AppError(422, "no_such_question", "No such question", "Pick one of this session's questions.")
    await _profile(ctx)
    q = sess.questions[body.index]["question"]
    conv = Conversation(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, created_by=ctx.principal.id,
                        title=f"Mock interview · {sess.role_title}"[:200])
    ctx.session.add(conv)
    await ctx.session.flush()
    actx = AgentContext(session=ctx.session, user_id=ctx.principal.id, org_id=ctx.workspace.org_id,
                        workspace_id=ctx.workspace.id, workspace_name=ctx.workspace.name, product="freelancer",
                        role=ctx.role, provider=provider, embedder=embedder, research=research,
                        conversation_id=conv.id, request=ctx.request)
    msg = f"Mock interview for: {sess.role_title}\nQuestion: {q}\nMy answer: {body.answer}"
    result = await orchestrator.run(actx, RunRequest(message=msg, conversation=conv, agent="freelancer.answer_coach"))
    entry = {"index": body.index, "answer": body.answer, "feedback": result.output, "run_id": str(result.run.id),
             "feedback_text": result.assistant_message.content, "at": datetime.now(UTC).isoformat()}
    sess.answers = [*[x for x in sess.answers if x["index"] != body.index], entry]
    await ctx.session.flush()
    return entry


@router.post("/interviews/{sid}/complete", response_model=InterviewOut)
async def complete_interview(sid: uuid.UUID, ctx: WsCtx = Depends(fl_ctx)):
    await ctx.require("ws.write")
    sess = await _get(ctx, InterviewSession, sid, "interview")
    sess.status = "completed"
    await ctx.session.flush()
    await ctx.session.refresh(sess)
    return sess
