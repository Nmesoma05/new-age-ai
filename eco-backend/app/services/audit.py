"""Append-only audit log for important account and workspace actions."""
from __future__ import annotations

import json
import uuid

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clientip import client_ip

# Keys never written into audit metadata, even if a caller passes them.
_REDACT = {"password", "token", "secret", "credentials", "api_key", "authorization"}


def _ip(request: Request | None) -> str | None:
    return client_ip(request)  # the person's address, not our web server's (QA BUG-10)


async def record(session: AsyncSession, action: str, *, actor_id: uuid.UUID | None, org_id: uuid.UUID | None = None,
                 workspace_id: uuid.UUID | None = None, target_type: str | None = None, target_id: object = None,
                 metadata: dict | None = None, request: Request | None = None) -> None:
    meta = {k: v for k, v in (metadata or {}).items() if k.lower() not in _REDACT}
    # Plain INSERT without RETURNING: writers may append, but only org admins may read the log (RLS).
    await session.execute(text(
        "INSERT INTO audit_events (action, actor_user_id, org_id, workspace_id, target_type, target_id, metadata, "
        "ip, user_agent) VALUES (:action, :actor, :org, :ws, :tt, :tid, CAST(:meta AS jsonb), CAST(:ip AS inet), :ua)"),
        {"action": action, "actor": actor_id, "org": org_id, "ws": workspace_id, "tt": target_type,
         "tid": str(target_id) if target_id is not None else None, "meta": json.dumps(meta, default=str),
         "ip": _ip(request), "ua": (request.headers.get("user-agent", "")[:300] if request else None)})
