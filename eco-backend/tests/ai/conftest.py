"""Fixtures for engine tests. The database, RLS, files and retrieval are real; only the LLM is scripted."""
from __future__ import annotations

import contextlib
import uuid

import pytest
from sqlalchemy import func, select

from app.ai.context import AgentContext
from app.ai.providers.embeddings import HashEmbedder


@pytest.fixture
def agent_ctx():
    """Open a user-scoped transaction (RLS active) and build the AgentContext the orchestrator would build."""
    @contextlib.asynccontextmanager
    async def _ctx(acct, workspace_id, provider=None, research=None):
        from app.core.db import transaction
        from app.models import Workspace
        async with transaction(acct.user_id) as s:
            ws, role = (await s.execute(select(Workspace, func.app.ws_role(Workspace.id))
                                        .where(Workspace.id == uuid.UUID(str(workspace_id))))).one()
            yield AgentContext(session=s, user_id=acct.user_id, org_id=ws.org_id, workspace_id=ws.id,
                               workspace_name=ws.name, product=ws.product, role=role, provider=provider,
                               embedder=HashEmbedder(1536), research=research)
    return _ctx


@pytest.fixture
def upload(client):
    async def _up(acct, ws, name, data, ctype="text/plain"):
        r = await client.post(f"/v1/workspaces/{ws}/documents", headers=acct.h, files={"file": (name, data, ctype)})
        assert r.status_code == 201, r.text
        return r.json()
    return _up
