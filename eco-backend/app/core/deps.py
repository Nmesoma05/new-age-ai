"""Request dependencies: one transaction per request, authenticated principal, tenant scoping."""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, Header, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_engine, set_tenant, system_context
from app.core.errors import AppError, forbidden, not_found
from app.core.permissions import org_can, ws_can
from app.core.security import decode_access_token
from app.models import Organisation, User, Workspace
from app.services import billing


async def get_session() -> AsyncIterator[AsyncSession]:
    from app.core import db as dbmod
    get_engine()
    assert dbmod._sessionmaker is not None
    async with dbmod._sessionmaker() as session:
        async with session.begin():
            await set_tenant(session, None)
            yield session


@dataclass
class Principal:
    user: User
    session: AsyncSession

    @property
    def id(self) -> uuid.UUID:
        return self.user.id


async def get_principal(session: AsyncSession = Depends(get_session),
                        authorization: str | None = Header(default=None)) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError(401, "unauthenticated", "Unauthenticated", "Send a bearer access token.",
                       headers={"WWW-Authenticate": "Bearer"})
    claims = decode_access_token(authorization[7:].strip())
    s = get_settings()
    async with system_context(session):
        if s.auth_mode == "local":
            try:
                uid = uuid.UUID(claims["sub"])
            except ValueError:
                raise AppError(401, "invalid_token", "Unauthenticated", "Sign in again.") from None
            user = await session.get(User, uid)
        else:
            user = (await session.execute(select(User).where(User.external_subject == claims["sub"]))).scalar_one_or_none()
            if user is None:
                from app.services.accounts import provision_external_user
                user = await provision_external_user(session, claims)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise AppError(401, "invalid_token", "Unauthenticated", "Sign in again.")
    issued_ms = claims.get("iat_ms") or int(claims.get("iat", 0)) * 1000
    if user.password_changed_at is not None and s.auth_mode == "local" and \
            issued_ms < int(user.password_changed_at.timestamp() * 1000):
        raise AppError(401, "invalid_token", "Unauthenticated", "Your password changed. Sign in again.")
    await set_tenant(session, user.id)
    return Principal(user=user, session=session)


# ------------------------------------------------------------------ organisation scope
@dataclass
class OrgCtx:
    principal: Principal
    org: Organisation
    role: str

    def require(self, permission: str) -> None:
        if not org_can(self.role, permission):
            raise forbidden("Your role in this organisation can't do that.")


async def org_ctx(org_id: uuid.UUID, p: Principal = Depends(get_principal)) -> OrgCtx:
    org = await p.session.get(Organisation, org_id)  # RLS hides orgs you don't belong to
    if org is None or org.deleted_at is not None:
        raise not_found("organisation")
    role = (await p.session.execute(text("SELECT app.org_role(:o)"), {"o": org_id})).scalar_one()
    if role is None:
        raise not_found("organisation")
    return OrgCtx(principal=p, org=org, role=role)


# ------------------------------------------------------------------ workspace scope
@dataclass
class WsCtx:
    principal: Principal
    workspace: Workspace
    role: str
    request: Request

    @property
    def session(self) -> AsyncSession:
        return self.principal.session

    async def require(self, permission: str) -> None:
        if not ws_can(self.role, permission):
            raise forbidden("Your role in this workspace can't do that. Ask a workspace admin for access.")
        if permission != "ws.read":
            ent = await billing.entitlements(self.session, self.workspace.org_id)
            if await billing.workspace_is_read_only(self.session, self.workspace, ent):
                raise forbidden("This workspace is read-only because your plan allows fewer workspaces. "
                                "Upgrade or delete another workspace to edit it.", code="plan_limit_read_only")


async def ws_ctx(workspace_id: uuid.UUID, request: Request, p: Principal = Depends(get_principal)) -> WsCtx:
    row = (await p.session.execute(
        select(Workspace, func.app.ws_role(Workspace.id)).where(Workspace.id == workspace_id,
                                                                   Workspace.deleted_at.is_(None))
    )).first()
    if row is None or row[1] is None or row[1] == "client_approver":
        raise not_found("workspace")
    return WsCtx(principal=p, workspace=row[0], role=row[1], request=request)
