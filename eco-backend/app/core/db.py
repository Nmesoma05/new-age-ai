"""Database sessions with tenant context.

Every request runs in ONE transaction. Before any query the transaction sets:
  app.user_id  -> the authenticated user's id ('' when anonymous)
  app.context  -> 'user' (default) or 'system' for narrow server-side paths
with set_config(..., is_local => true), so values vanish at COMMIT/ROLLBACK and never leak
between pooled connections. Row-level security policies (migration 0002) read these values.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        s = get_settings()
        _engine = create_async_engine(s.database_url.get_secret_value(), pool_size=s.db_pool_size,
                                      pool_pre_ping=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def set_tenant(session: AsyncSession, user_id: uuid.UUID | None, context: str = "user") -> None:
    await session.execute(
        text("SELECT set_config('app.user_id', :uid, true), set_config('app.context', :ctx, true)"),
        {"uid": str(user_id) if user_id else "", "ctx": context},
    )


@asynccontextmanager
async def system_context(session: AsyncSession, user_id: uuid.UUID | None = None) -> AsyncIterator[None]:
    """Temporarily switch the current transaction to 'system' context, then restore 'user'.

    Use only for server-side writes that users must not control directly (auth tokens,
    usage counters, subscription changes, webhook processing).
    """
    await session.execute(text("SELECT set_config('app.context', 'system', true)"))
    try:
        yield
        await session.flush()  # pending ORM writes must reach the DB while still in system context
    finally:
        await session.execute(text("SELECT set_config('app.context', 'user', true)"))
        if user_id is not None:
            await session.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(user_id)})


@asynccontextmanager
async def transaction(user_id: uuid.UUID | None = None, context: str = "user") -> AsyncIterator[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    async with _sessionmaker() as session:
        async with session.begin():
            await set_tenant(session, user_id, context)
            yield session
