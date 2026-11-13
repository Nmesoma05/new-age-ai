"""Subscriptions, entitlements and AI usage.

Paid plans: unlimited AI while the paid period is active (incl. after cancelling, until period_end).
Free plan (no live subscription): a monthly count of successful AI generations.
Fair use: per-user requests/minute and a monthly per-user provider-cost threshold (not published).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import system_context
from app.core.errors import AppError
from app.models import AiUsageRecord, Plan, Subscription, UsageCounter, Workspace

log = logging.getLogger("eco.billing")


@dataclass(frozen=True)
class Entitlements:
    plan: Plan
    subscription: Subscription | None

    @property
    def is_paid_active(self) -> bool:
        return self.plan.is_paid


def month_start(now: datetime | None = None) -> date:
    n = now or datetime.now(UTC)
    return date(n.year, n.month, 1)


async def entitlements(session: AsyncSession, org_id: uuid.UUID, now: datetime | None = None) -> Entitlements:
    now = now or datetime.now(UTC)
    sub = (await session.execute(
        select(Subscription).where(Subscription.org_id == org_id,
                                   Subscription.status.in_(("active", "past_due", "cancelled")))
    )).scalar_one_or_none()
    live = None
    if sub is not None:
        until = sub.period_end
        if sub.status == "past_due" and sub.grace_until:
            until = max(sub.period_end, sub.grace_until)
        if sub.period_start <= now < until:
            live = sub
    code = live.plan_code if live else "free"
    plan = (await session.execute(select(Plan).where(Plan.code == code))).scalar_one()
    return Entitlements(plan=plan, subscription=live)


async def free_used(session: AsyncSession, org_id: uuid.UUID, now: datetime | None = None) -> int:
    row = (await session.execute(select(UsageCounter.free_generations_used).where(
        UsageCounter.org_id == org_id, UsageCounter.period_month == month_start(now)))).scalar_one_or_none()
    return row or 0


async def workspace_is_read_only(session: AsyncSession, ws: Workspace, ent: Entitlements) -> bool:
    """Workspaces beyond the plan limit (oldest kept writable) become read-only; never deleted."""
    rank = (await session.execute(text(
        "SELECT count(*) FROM workspaces WHERE org_id = :org AND deleted_at IS NULL "
        "AND (created_at, id) <= (:ts, :id)"), {"org": ws.org_id, "ts": ws.created_at, "id": ws.id})).scalar_one()
    return rank > ent.plan.max_workspaces


_alerted_day: date | None = None


async def _check_daily_budget(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Platform-wide cost ceiling (AI_DAILY_BUDGET_USD). Pauses NEW generations for everyone until midnight UTC;
    nothing already saved is affected. Logs a warning at AI_BUDGET_ALERT_RATIO and a critical line at the cap, so
    the alert reaches whoever is on call before customers notice."""
    global _alerted_day
    s = get_settings()
    if s.ai_daily_budget_usd <= 0:
        return
    now = datetime.now(UTC)
    day = datetime(now.year, now.month, now.day, tzinfo=UTC)
    async with system_context(session, user_id):
        spent = Decimal((await session.execute(select(func.coalesce(func.sum(AiUsageRecord.cost_usd), 0)).where(
            AiUsageRecord.created_at >= day))).scalar_one())
    budget = Decimal(str(s.ai_daily_budget_usd))
    if spent >= budget:
        log.critical("ai daily budget reached: generations paused",
                     extra={"spent_usd": float(spent), "budget_usd": float(budget)})
        retry = int((day + timedelta(days=1) - now).total_seconds()) + 1
        raise AppError(503, "ai_paused", "AI drafting is paused for today",
                       "We've reached today's AI usage limit for the whole service. Everything you've saved is safe. "
                       "Drafting resumes at midnight UTC.", headers={"Retry-After": str(retry)})
    if spent >= budget * Decimal(str(s.ai_budget_alert_ratio)) and _alerted_day != day.date():
        _alerted_day = day.date()
        log.warning("ai daily budget alert", extra={"spent_usd": float(spent), "budget_usd": float(budget)})


async def check_can_generate(session: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID) -> Entitlements:
    s = get_settings()
    await _check_daily_budget(session, user_id)
    ent = await entitlements(session, org_id)
    # one user request may make several model calls; the per-minute limit counts requests (runs)
    recent = (await session.execute(select(func.count(func.distinct(func.coalesce(AiUsageRecord.run_id,
                                                                                    AiUsageRecord.id)))).where(
        AiUsageRecord.user_id == user_id,
        AiUsageRecord.created_at > func.now() - text("interval '60 seconds'")))).scalar_one()
    if recent >= s.ai_rate_limit_per_minute:
        raise AppError(429, "rate_limited", "Slow down", "Too many requests in a minute. Try again shortly.",
                       headers={"Retry-After": "30"})
    if ent.is_paid_active:
        spent = (await session.execute(select(func.coalesce(func.sum(AiUsageRecord.cost_usd), 0)).where(
            AiUsageRecord.user_id == user_id, AiUsageRecord.org_id == org_id,
            AiUsageRecord.created_at >= month_start()))).scalar_one()
        if Decimal(spent) >= Decimal(str(s.fair_use_monthly_usd_per_user)):
            raise AppError(429, "fair_use_review", "Taking a short break",
                           "Your usage is far above normal this month, so requests are slowed while we review. "
                           "Your work is safe.", headers={"Retry-After": "300"})
        return ent
    # Free plan: lock this month's counter row until the request commits (QA BUG-14). Without the lock, parallel
    # requests all read "29 of 30" and all go through. Only Free generations queue, and only per organisation.
    async with system_context(session, user_id):
        await session.execute(insert(UsageCounter).values(org_id=org_id, period_month=month_start(),
                                                          free_generations_used=0).on_conflict_do_nothing())
        used = (await session.execute(select(UsageCounter.free_generations_used).where(
            UsageCounter.org_id == org_id, UsageCounter.period_month == month_start()).with_for_update())).scalar_one()
    if used >= (ent.plan.free_monthly_limit or 0):
        raise AppError(402, "free_limit_reached", "Free limit reached",
                       f"You've used your {ent.plan.free_monthly_limit} free drafts this month. "
                       "Upgrade for unlimited drafts, or wait for the monthly reset.")
    return ent


async def record_generation(session: AsyncSession, *, ent: Entitlements, org_id: uuid.UUID, user_id: uuid.UUID,
                            workspace_id: uuid.UUID | None, agent: str, model: str, succeeded: bool,
                            tokens_in: int, tokens_out: int, latency_ms: int, error_code: str | None = None,
                            run_id: uuid.UUID | None = None, count_free: bool = True) -> AiUsageRecord:
    s = get_settings()
    p_in, p_out = s.ai_model_prices.get(model, [s.ai_price_in_per_1m_usd, s.ai_price_out_per_1m_usd])
    cost = (Decimal(tokens_in) * Decimal(str(p_in)) + Decimal(tokens_out) * Decimal(str(p_out))) / Decimal(1_000_000)
    # Free plan: one counted generation per successful request, however many model calls it took.
    counted = succeeded and count_free and not ent.is_paid_active
    rec = AiUsageRecord(org_id=org_id, workspace_id=workspace_id, user_id=user_id, agent=agent, model=model,
                        status="succeeded" if succeeded else "failed", tokens_in=tokens_in, tokens_out=tokens_out,
                        cost_usd=cost.quantize(Decimal("0.000001")), counted_free=counted, latency_ms=latency_ms,
                        error_code=error_code, run_id=run_id)
    session.add(rec)
    await session.flush()
    if counted:
        async with system_context(session, user_id):
            stmt = insert(UsageCounter).values(org_id=org_id, period_month=month_start(), free_generations_used=1)
            stmt = stmt.on_conflict_do_update(
                index_elements=[UsageCounter.org_id, UsageCounter.period_month],
                set_={"free_generations_used": UsageCounter.free_generations_used + 1})
            await session.execute(stmt)
    return rec
