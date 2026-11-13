"""AI conversations and saved outputs (assets with versions)."""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select

from app.ai import orchestrator
from app.ai.context import AgentContext
from app.ai.orchestrator import RunRequest
from app.ai.providers import get_embedder, get_llm_provider
from app.ai.providers.base import LLMProvider
from app.ai.research import get_research_backend
from app.core.deps import WsCtx, ws_ctx
from app.core.errors import AppError, not_found
from app.core.pagination import page_of, paginate
from app.models import Asset, AssetVersion, Conversation, Message, Project
from app.schemas.common import (
    AssetIn,
    AssetOut,
    AssetPatch,
    AssetVersionIn,
    AssetVersionOut,
    ConversationIn,
    ConversationOut,
    ExchangeOut,
    MessageIn,
    MessageOut,
    RunSummaryOut,
)
from app.services import audit

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["conversations", "assets"])


# ---------------------------------------------------------------- conversations
@router.get("/conversations")
async def list_conversations(cursor: str | None = None, limit: int = 25, ctx: WsCtx = Depends(ws_ctx)):
    stmt = paginate(select(Conversation).where(Conversation.workspace_id == ctx.workspace.id), Conversation, cursor, limit)
    rows = (await ctx.session.execute(stmt)).scalars().all()
    return page_of(list(rows), limit, lambda r: ConversationOut.model_validate(r))


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(body: ConversationIn, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.ai.run")
    conv = Conversation(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, created_by=ctx.principal.id,
                        title=body.title)
    ctx.session.add(conv)
    await ctx.session.flush()
    await ctx.session.refresh(conv)
    return conv


async def _conv(ctx: WsCtx, conversation_id: uuid.UUID) -> Conversation:
    conv = await ctx.session.get(Conversation, conversation_id)
    if conv is None or conv.workspace_id != ctx.workspace.id:
        raise not_found("conversation")
    return conv


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: uuid.UUID, cursor: str | None = None, limit: int = 50,
                        ctx: WsCtx = Depends(ws_ctx)):
    await _conv(ctx, conversation_id)
    stmt = paginate(select(Message).where(Message.conversation_id == conversation_id), Message, cursor, limit)
    rows = (await ctx.session.execute(stmt)).scalars().all()
    return page_of(list(rows), limit, lambda r: MessageOut.model_validate(r))


@router.post("/conversations/{conversation_id}/messages", response_model=ExchangeOut, status_code=201)
async def send_message(conversation_id: uuid.UUID, body: MessageIn, ctx: WsCtx = Depends(ws_ctx),
                       provider: LLMProvider = Depends(get_llm_provider), embedder=Depends(get_embedder),
                       research=Depends(get_research_backend)):
    """Send a message to the assistant. The orchestrator routes it, runs the right agent(s) with tools, validates
    the output and stores the exchange. External actions come back as pending_actions awaiting approval."""
    await ctx.require("ws.ai.run")
    conv = await _conv(ctx, conversation_id)
    actx = AgentContext(session=ctx.session, user_id=ctx.principal.id, org_id=ctx.workspace.org_id,
                        workspace_id=ctx.workspace.id, workspace_name=ctx.workspace.name, product=ctx.workspace.product,
                        role=ctx.role, provider=provider, embedder=embedder, research=research,
                        conversation_id=conv.id, request=ctx.request)
    result = await orchestrator.run(actx, RunRequest(message=body.content, conversation=conv, agent=body.agent,
                                                     document_ids=body.document_ids, save=body.save_as_asset,
                                                     asset_type=body.asset_type))
    r = result.run
    return ExchangeOut(
        user_message=MessageOut.model_validate(result.user_message),
        assistant_message=MessageOut.model_validate(result.assistant_message),
        run=RunSummaryOut(id=r.id, agent=r.agent, status=r.status, output=result.output, warnings=r.warnings,
                          uncertainties=r.uncertainties, injection_detected=bool(r.injection_flags),
                          pending_actions=result.pending_actions, saved_asset_id=result.saved_asset_id,
                          memory_saved=result.memory_saved))


# ---------------------------------------------------------------- assets (saved outputs)
@router.get("/assets")
async def list_assets(cursor: str | None = None, limit: int = 25, status: str | None = None, tag: str | None = None,
                      ctx: WsCtx = Depends(ws_ctx)):
    stmt = select(Asset).where(Asset.workspace_id == ctx.workspace.id, Asset.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Asset.status == status)
    if tag:
        stmt = stmt.where(Asset.tags.contains([tag]))
    rows = (await ctx.session.execute(paginate(stmt, Asset, cursor, limit))).scalars().all()
    return page_of(list(rows), limit, lambda r: AssetOut.model_validate(r))


@router.post("/assets", response_model=AssetOut, status_code=201)
async def create_asset(body: AssetIn, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.write")
    if body.project_id:
        pr = await ctx.session.get(Project, body.project_id)
        if pr is None or pr.workspace_id != ctx.workspace.id:
            raise not_found("project")
    asset = Asset(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, project_id=body.project_id,
                  type=body.type, title=body.title, tags=body.tags, created_by=ctx.principal.id)
    ctx.session.add(asset)
    await ctx.session.flush()
    ctx.session.add(AssetVersion(asset_id=asset.id, workspace_id=asset.workspace_id, org_id=asset.org_id, version=1,
                                 body=body.body, body_text=body.body_text, source="human", author_id=ctx.principal.id))
    await ctx.session.flush()
    await ctx.session.refresh(asset)
    await audit.record(ctx.session, "asset.created", actor_id=ctx.principal.id, org_id=asset.org_id,
                       workspace_id=asset.workspace_id, target_type="asset", target_id=asset.id,
                       metadata={"type": asset.type}, request=ctx.request)
    return asset


async def _asset(ctx: WsCtx, asset_id: uuid.UUID) -> Asset:
    a = await ctx.session.get(Asset, asset_id)
    if a is None or a.workspace_id != ctx.workspace.id or a.deleted_at is not None:
        raise not_found("asset")
    return a


@router.get("/assets/{asset_id}", response_model=AssetOut)
async def get_asset(asset_id: uuid.UUID, ctx: WsCtx = Depends(ws_ctx)):
    return await _asset(ctx, asset_id)


@router.patch("/assets/{asset_id}", response_model=AssetOut)
async def update_asset(asset_id: uuid.UUID, body: AssetPatch, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.write")
    a = await _asset(ctx, asset_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("status") == "approved" and ctx.role != "admin":
        raise AppError(403, "approval_required", "Approval needed", "Only a workspace admin can approve.")
    before = a.status
    for k, v in changes.items():
        setattr(a, k, v)
    await ctx.session.flush()
    await ctx.session.refresh(a)
    if "status" in changes and changes["status"] != before:
        await audit.record(ctx.session, "asset.status_changed", actor_id=ctx.principal.id, org_id=a.org_id,
                           workspace_id=a.workspace_id, target_type="asset", target_id=a.id,
                           metadata={"from": before, "to": a.status}, request=ctx.request)
    return a


@router.get("/assets/{asset_id}/versions", response_model=list[AssetVersionOut])
async def list_versions(asset_id: uuid.UUID, ctx: WsCtx = Depends(ws_ctx)):
    await _asset(ctx, asset_id)
    return (await ctx.session.execute(select(AssetVersion).where(AssetVersion.asset_id == asset_id)
                                      .order_by(AssetVersion.version.desc()))).scalars().all()


@router.post("/assets/{asset_id}/versions", response_model=AssetVersionOut, status_code=201)
async def add_version(asset_id: uuid.UUID, body: AssetVersionIn, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.write")
    a = await _asset(ctx, asset_id)
    nxt = (await ctx.session.execute(select(func.max(AssetVersion.version)).where(AssetVersion.asset_id == a.id))).scalar_one() + 1
    v = AssetVersion(asset_id=a.id, workspace_id=a.workspace_id, org_id=a.org_id, version=nxt, body=body.body,
                     body_text=body.body_text, source="human", author_id=ctx.principal.id)
    ctx.session.add(v)
    a.current_version = nxt
    if a.status == "approved":
        a.status = "in_review"  # editing approved content needs a fresh approval
    await ctx.session.flush()
    await ctx.session.refresh(v)
    return v


@router.delete("/assets/{asset_id}", status_code=204)
async def delete_asset(asset_id: uuid.UUID, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.write")
    a = await _asset(ctx, asset_id)
    a.deleted_at = datetime.now(UTC)
    await ctx.session.flush()
    await audit.record(ctx.session, "asset.deleted", actor_id=ctx.principal.id, org_id=a.org_id,
                       workspace_id=a.workspace_id, target_type="asset", target_id=a.id, request=ctx.request)
    return Response(status_code=204)
