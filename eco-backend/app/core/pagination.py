"""Cursor pagination on (created_at DESC, id DESC)."""
from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import Select, and_, or_

from app.core.errors import AppError

T = TypeVar("T")
MAX_LIMIT = 100


class Page(BaseModel, Generic[T]):
    data: list[T]
    next_cursor: str | None = None


def encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    raw = json.dumps([created_at.isoformat(), str(row_id)]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        ts, rid = json.loads(raw)
        return datetime.fromisoformat(ts), uuid.UUID(rid)
    except Exception:
        raise AppError(400, "invalid_cursor", "Invalid cursor", "Start again without a cursor.") from None


def paginate(stmt: Select, model, cursor: str | None, limit: int) -> Select:
    if not 1 <= limit <= MAX_LIMIT:
        raise AppError(400, "invalid_limit", "Invalid limit", f"limit must be between 1 and {MAX_LIMIT}.")
    if cursor:
        ts, rid = decode_cursor(cursor)
        stmt = stmt.where(or_(model.created_at < ts, and_(model.created_at == ts, model.id < rid)))
    return stmt.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)


def page_of(rows: list, limit: int, to_out) -> dict:
    more = len(rows) > limit
    rows = rows[:limit]
    nxt = encode_cursor(rows[-1].created_at, rows[-1].id) if more and rows else None
    return {"data": [to_out(r) for r in rows], "next_cursor": nxt}
