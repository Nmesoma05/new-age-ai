"""Memory.

Three layers, all bound to one workspace (nothing crosses workspaces, even for the same person):
  - conversation memory: the conversation's rolling summary + its recent messages
  - workspace memory:    memory_items with visibility 'workspace' (brand rules, decisions, facts)
  - private memory:      memory_items with visibility 'private' (only the author sees or retrieves them)

Writes: agents may *propose* memories, but each proposal must quote the user's own message from this turn.
A proposal whose quote isn't found there (e.g. it came from a document) is dropped. Proposals are stored as
'proposed' unless the user explicitly asked to remember something, and only 'active' items are retrieved.
"""
from __future__ import annotations

import re
import uuid
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.ai.context import AgentContext
from app.models import Conversation, MemoryItem, Message

RECENT_MESSAGES = 12


class MemoryCandidate(BaseModel):
    kind: Literal["fact", "preference", "decision", "brand_rule", "constraint"]
    content: str = Field(min_length=3, max_length=500, description="The thing to remember, in one sentence.")
    user_quote: str = Field(min_length=3, max_length=300,
                            description="Exact words from the user's latest message that support this memory.")
    visibility: Literal["workspace", "private"] = "workspace"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower().strip("\"'“”‘’ ")


def quote_is_from_user(candidate: MemoryCandidate, user_message: str) -> bool:
    q = _norm(candidate.user_quote)
    return len(q) >= 8 and q in _norm(user_message)


async def add_memory(ctx: AgentContext, *, content: str, kind: str, visibility: str, source: str, status: str,
                     run_id: uuid.UUID | None = None, project_id: uuid.UUID | None = None) -> MemoryItem | None:
    dup = (await ctx.session.execute(select(MemoryItem.id).where(
        MemoryItem.workspace_id == ctx.workspace_id, MemoryItem.status != "archived",
        func.lower(MemoryItem.content) == content.strip().lower()))).first()
    if dup:
        return None
    vec, model = None, None
    if ctx.embedder is not None:
        try:
            vec, model = (await ctx.embedder.embed([content]))[0], ctx.embedder.model
        except Exception:
            vec = None
    item = MemoryItem(workspace_id=ctx.workspace_id, org_id=ctx.org_id, project_id=project_id, visibility=visibility,
                      owner_user_id=ctx.user_id, kind=kind, content=content.strip(), source=source, status=status,
                      source_run_id=run_id, embedding=vec, embedding_model=model)
    ctx.session.add(item)
    await ctx.session.flush()
    return item


async def save_candidates(ctx: AgentContext, candidates: list[MemoryCandidate], user_message: str, *,
                          explicit: bool, run_id: uuid.UUID | None) -> tuple[list[MemoryItem], int]:
    """Returns (saved items, number rejected for not quoting the user)."""
    saved, rejected = [], 0
    for c in candidates[:5]:
        if not quote_is_from_user(c, user_message):
            rejected += 1
            continue
        item = await add_memory(ctx, content=c.content, kind=c.kind, visibility=c.visibility,
                                source="user_stated" if explicit else "agent_proposed",
                                status="active" if explicit else "proposed", run_id=run_id)
        if item:
            saved.append(item)
    return saved, rejected


async def conversation_window(ctx: AgentContext, conversation: Conversation) -> tuple[str, list[Message]]:
    """Rolling summary plus the most recent messages after it, all from this one conversation."""
    ctx.assert_in_scope(conversation.workspace_id)
    stmt = select(Message).where(Message.conversation_id == conversation.id)
    if conversation.summary_through is not None:
        stmt = stmt.where(Message.created_at > conversation.summary_through)
    rows = (await ctx.session.execute(stmt.order_by(Message.created_at.desc(), Message.id.desc())
                                      .limit(RECENT_MESSAGES))).scalars().all()
    for m in rows:
        ctx.assert_in_scope(m.workspace_id)
    return conversation.summary, list(reversed(rows))
