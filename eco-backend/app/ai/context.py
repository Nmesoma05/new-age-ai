"""The scope an agent run is allowed to see. Built only from the authenticated request, never from model output."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.base import EmbeddingProvider, LLMProvider


class ContextLeakError(RuntimeError):
    """Raised if anything outside the run's workspace reaches the context builder (defence in depth over RLS)."""


@dataclass
class AgentContext:
    session: AsyncSession
    user_id: uuid.UUID
    org_id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_name: str
    product: str  # creator | business | freelancer
    role: str     # effective workspace role: admin | editor | viewer
    provider: LLMProvider
    embedder: EmbeddingProvider | None = None
    research: object | None = None  # ResearchBackend
    conversation_id: uuid.UUID | None = None
    request: Request | None = None

    def assert_in_scope(self, workspace_id: uuid.UUID | None) -> None:
        if workspace_id != self.workspace_id:
            raise ContextLeakError("context item from another workspace")
