"""Per-IP sliding-window limits for unauthenticated endpoints (sign-in, sign-up, password reset). QA BUG-11.

Complements the per-account lockout: that stops guessing one account's password, this stops one address trying
many accounts or creating accounts in bulk. Counters live in Postgres (auth_attempts), so every worker and every
instance sees the same numbers. Rows older than a day are pruned opportunistically. Unknown IP (see clientip.py) =
no IP limit; the per-account controls still apply.
"""
from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.core.db import transaction
from app.core.errors import AppError


async def reset() -> None:
    async with transaction(None, context="system") as s:
        await s.execute(text("DELETE FROM auth_attempts"))


async def check(bucket: str, ip: str | None, limit: int, window: float) -> None:
    """Raise 429 if `ip` already has `limit` hits in `window` seconds for this bucket."""
    if ip is None or limit <= 0:
        return
    since = datetime.now(UTC) - timedelta(seconds=window)
    async with transaction(None, context="system") as s:
        n, oldest = (await s.execute(text(
            "SELECT count(*), min(at) FROM auth_attempts WHERE bucket = :b AND ip = CAST(:ip AS inet) AND at > :since"),
            {"b": bucket, "ip": ip, "since": since})).one()
    if n >= limit:
        retry = max(1, math.ceil((oldest + timedelta(seconds=window) - datetime.now(UTC)).total_seconds()))
        raise AppError(429, "rate_limited", "Too many attempts",
                       "Too many attempts from your network. Wait a little and try again.",
                       headers={"Retry-After": str(retry)}, extra={"retry_after": retry})


async def hit(bucket: str, ip: str | None) -> None:
    if ip is None:
        return
    async with transaction(None, context="system") as s:
        await s.execute(text("INSERT INTO auth_attempts (bucket, ip) VALUES (:b, CAST(:ip AS inet))"),
                        {"b": bucket, "ip": ip})
        if random.random() < 0.01:  # keep the table small without a separate job
            await s.execute(text("DELETE FROM auth_attempts WHERE at < now() - interval '1 day'"))
