"""Assistant transparency and control: agent runs (with tool calls), approval of proposed external actions,
and workspace memory."""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select, text, update

from app.ai import actions
from app.ai.context import AgentContext
from app.ai.memory import add_memory
from app.ai.providers import get_embedder
from app.core.db import system_context, transaction
from app.core.deps import WsCtx, ws_ctx
from app.core.errors import AppError, forbidden, not_found
from app.core.pagination import page_of, paginate
from app.integrations.http import IntegrationError, OutcomeUnknown
from app.models import (
    AgentRun,
    Integration,
    MemoryItem,
    PendingAction,
    Project,
    ToolCallRecord,
)
from app.schemas.common import (
    ActionDecisionIn,
    MemoryIn,
    MemoryOut,
    MemoryPatch,
    PendingActionOut,
    RunDetailOut,
    RunOut,
    ToolCallOut,
)
from app.services import audit

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["assistant"])


# ---------------------------------------------------------------- runs
@router.get("/runs")
async def list_runs(cursor: str | None = None, limit: int = 25, ctx: WsCtx = Depends(ws_ctx)):
    stmt = paginate(select(AgentRun).where(AgentRun.workspace_id == ctx.workspace.id), AgentRun, cursor, limit)
    rows = (await ctx.session.execute(stmt)).scalars().all()
    return page_of(list(rows), limit, lambda r: RunOut.model_validate(r))


@router.get("/runs/{run_id}", response_model=RunDetailOut)
async def get_run(run_id: uuid.UUID, ctx: WsCtx = Depends(ws_ctx)):
    run = await ctx.session.get(AgentRun, run_id)
    if run is None or run.workspace_id != ctx.workspace.id:
        raise not_found("run")
    calls = (await ctx.session.execute(select(ToolCallRecord).where(ToolCallRecord.run_id == run.id)
                                       .order_by(ToolCallRecord.created_at))).scalars().all()
    out = RunDetailOut.model_validate(run)
    out.tool_calls = [ToolCallOut.model_validate(c) for c in calls]
    return out


# ---------------------------------------------------------------- approval-gated actions
@router.get("/actions")
async def list_actions(status: str | None = Query(default=None, pattern="^(awaiting_approval|approved|rejected|executed|failed|expired)$"),
                       cursor: str | None = None, limit: int = 25, ctx: WsCtx = Depends(ws_ctx)):
    stmt = select(PendingAction).where(PendingAction.workspace_id == ctx.workspace.id)
    if status:
        stmt = stmt.where(PendingAction.status == status)
    rows = (await ctx.session.execute(paginate(stmt, PendingAction, cursor, limit))).scalars().all()
    return page_of(list(rows), limit, lambda r: PendingActionOut.model_validate(r))


async def _decidable(ctx: WsCtx, action_id: uuid.UUID) -> PendingAction:
    a = await ctx.session.get(PendingAction, action_id)
    if a is None or a.workspace_id != ctx.workspace.id:
        raise not_found("action")
    if ctx.role != "admin":
        raise forbidden("Only a workspace admin can approve or reject actions.")
    if a.status == "awaiting_approval" and a.expires_at <= datetime.now(UTC):
        # Persist the expiry in its own transaction: the error below rolls back the request's transaction.
        async with transaction(ctx.principal.id) as s2:
            await s2.execute(update(PendingAction).where(PendingAction.id == a.id,
                                                         PendingAction.status == "awaiting_approval")
                             .values(status="expired"))
        raise AppError(409, "action_expired", "Expired", "This proposal expired. Ask the assistant again.")
    # Lock only after the role check: SELECT ... FOR UPDATE is also filtered by the UPDATE policy (admins only).
    # The lock stops two admins approving the same action at once.
    await ctx.session.refresh(a, with_for_update=True)
    if a.kind == "spend_money":
        org_role = (await ctx.session.execute(text("SELECT app.org_role(:o)"), {"o": a.org_id})).scalar_one()
        if org_role not in ("owner", "admin"):
            raise forbidden("Spending money needs an organisation owner or admin.")
    if a.status != "awaiting_approval":
        raise AppError(409, "action_already_decided", "Already decided", f"This action is already {a.status}.")
    return a


@router.post("/actions/{action_id}/approve", response_model=PendingActionOut)
async def approve_action(action_id: uuid.UUID, body: ActionDecisionIn | None = None, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.write")
    a = await _decidable(ctx, action_id)
    executor = actions.EXECUTORS.get(a.kind)
    if executor is None:
        raise AppError(409, "no_executor", "Can't carry this out yet",
                       "No connected integration can do this yet. Copy the content and do it yourself, or reject it.")
    async with system_context(ctx.session):
        integ = (await ctx.session.execute(select(Integration).where(
            Integration.workspace_id == a.workspace_id, Integration.provider == executor.provider,
            Integration.status == "connected").order_by(Integration.created_at.desc()))).scalars().first()
    if integ is None:
        raise AppError(409, "no_connection", "Account not connected",
                       "Connect the account this needs in Settings first. The action is still waiting for approval.")
    a.status, a.decided_by, a.decided_at = "approved", ctx.principal.id, datetime.now(UTC)
    await ctx.session.flush()
    await audit.record(ctx.session, "ai.action_approved", actor_id=ctx.principal.id, org_id=a.org_id,
                       workspace_id=a.workspace_id, target_type="pending_action", target_id=a.id,
                       metadata={"kind": a.kind, "from_untrusted": a.from_untrusted,
                                 "provider": executor.provider}, request=ctx.request)
    try:
        result = await executor.execute(a, integ, a.id)
        if not isinstance(result, dict) or not result.get("provider_ref"):
            a.status, a.result = "failed", {"error": "no_confirmation",
                                            "message": "The provider didn't confirm this happened."}
        else:
            a.status, a.result, a.executed_at = "executed", result, datetime.now(UTC)
    except OutcomeUnknown as e:
        a.status, a.result = "failed", {"error": "outcome_unknown", "message": e.message}
    except IntegrationError as e:
        a.status, a.result = "failed", {"error": e.code, "message": e.message}
    except Exception:
        a.status, a.result = "failed", {"error": "execution_failed"}
    await ctx.session.flush()
    await audit.record(ctx.session, f"ai.action_{a.status}", actor_id=ctx.principal.id, org_id=a.org_id,
                       workspace_id=a.workspace_id, target_type="pending_action", target_id=a.id,
                       metadata={"kind": a.kind}, request=ctx.request)
    await ctx.session.refresh(a)
    return a


@router.post("/actions/{action_id}/reject", response_model=PendingActionOut)
async def reject_action(action_id: uuid.UUID, body: ActionDecisionIn | None = None, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.write")
    a = await _decidable(ctx, action_id)
    a.status, a.decided_by, a.decided_at = "rejected", ctx.principal.id, datetime.now(UTC)
    a.result = {"reason": body.reason} if body and body.reason else {}
    await ctx.session.flush()
    await audit.record(ctx.session, "ai.action_rejected", actor_id=ctx.principal.id, org_id=a.org_id,
                       workspace_id=a.workspace_id, target_type="pending_action", target_id=a.id,
                       metadata={"kind": a.kind}, request=ctx.request)
    await ctx.session.refresh(a)
    return a


# ---------------------------------------------------------------- memory
@router.get("/memory")
async def list_memory(status: str = Query(default="active", pattern="^(active|proposed|archived)$"),
                      cursor: str | None = None, limit: int = 50, ctx: WsCtx = Depends(ws_ctx)):
    stmt = select(MemoryItem).where(MemoryItem.workspace_id == ctx.workspace.id, MemoryItem.status == status)
    rows = (await ctx.session.execute(paginate(stmt, MemoryItem, cursor, limit))).scalars().all()
    return page_of(list(rows), limit, lambda r: MemoryOut.model_validate(r))


@router.post("/memory", response_model=MemoryOut, status_code=201)
async def create_memory(body: MemoryIn, ctx: WsCtx = Depends(ws_ctx), embedder=Depends(get_embedder)):
    await ctx.require("ws.write")
    if body.project_id:
        pr = await ctx.session.get(Project, body.project_id)
        if pr is None or pr.workspace_id != ctx.workspace.id:
            raise not_found("project")
    actx = AgentContext(session=ctx.session, user_id=ctx.principal.id, org_id=ctx.workspace.org_id,
                        workspace_id=ctx.workspace.id, workspace_name=ctx.workspace.name, product=ctx.workspace.product,
                        role=ctx.role, provider=None, embedder=embedder)  # type: ignore[arg-type]
    item = await add_memory(actx, content=body.content, kind=body.kind, visibility=body.visibility,
                            source="user_stated", status="active", project_id=body.project_id)
    if item is None:
        raise AppError(409, "memory_exists", "Already remembered", "That's already in this workspace's memory.")
    await audit.record(ctx.session, "ai.memory_saved", actor_id=ctx.principal.id, org_id=item.org_id,
                       workspace_id=item.workspace_id, target_type="memory_item", target_id=item.id,
                       metadata={"status": "active", "kind": item.kind, "by": "user"}, request=ctx.request)
    await ctx.session.refresh(item)
    return item


async def _memory(ctx: WsCtx, memory_id: uuid.UUID) -> MemoryItem:
    m = await ctx.session.get(MemoryItem, memory_id)
    if m is None or m.workspace_id != ctx.workspace.id:
        raise not_found("memory")
    return m


@router.patch("/memory/{memory_id}", response_model=MemoryOut)
async def update_memory(memory_id: uuid.UUID, body: MemoryPatch, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.write")
    m = await _memory(ctx, memory_id)
    if body.status == "active" and m.status == "proposed":
        m.source = "user_confirmed"
    if body.status:
        m.status = body.status
    if body.content:
        m.content, m.embedding, m.embedding_model = body.content, None, None  # re-embedded lazily; FTS still works
    await ctx.session.flush()
    await ctx.session.refresh(m)
    return m


@router.delete("/memory/{memory_id}", status_code=204)
async def delete_memory(memory_id: uuid.UUID, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.write")
    m = await _memory(ctx, memory_id)
    await ctx.session.delete(m)
    await audit.record(ctx.session, "ai.memory_deleted", actor_id=ctx.principal.id, org_id=m.org_id,
                       workspace_id=m.workspace_id, target_type="memory_item", target_id=m.id, request=ctx.request)
    return Response(status_code=204)
