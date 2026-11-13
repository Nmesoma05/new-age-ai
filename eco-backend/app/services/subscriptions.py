"""Applying subscription changes. Runs only in 'system' context (webhooks, admin tooling)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Organisation, Plan, Subscription
from app.services import audit

PAID_PLANS = {"starter", "pro", "team"}


async def activate_period(session: AsyncSession, *, org_id: uuid.UUID, plan_code: str, provider: str,
                          provider_ref: str, days: int, auto_renew: bool, now: datetime | None = None) -> Subscription:
    """Start or extend a paid period. A prepaid renewal extends from the current end date, not from today."""
    if plan_code not in PAID_PLANS:
        raise ValueError("unknown paid plan")
    if not 1 <= days <= 400:
        raise ValueError("invalid period length")
    now = now or datetime.now(UTC)
    if await session.get(Organisation, org_id) is None or await session.get(Plan, plan_code) is None:
        raise ValueError("unknown org or plan")
    sub = (await session.execute(select(Subscription).where(
        Subscription.org_id == org_id, Subscription.status.in_(("active", "past_due", "cancelled"))))).scalar_one_or_none()
    if sub is not None and sub.period_end > now:
        start = sub.period_end if sub.plan_code == plan_code else now
        if sub.plan_code != plan_code:  # plan change: close the old row, open a new one from now
            sub.status = "expired"
            sub.period_end = max(now, sub.period_start + timedelta(seconds=1))
            await session.flush()
            sub = None
        else:
            sub.period_end = start + timedelta(days=days)
            sub.status, sub.auto_renew, sub.grace_until = "active", auto_renew, None
            sub.provider_ref = provider_ref
    else:
        if sub is not None:
            sub.status = "expired"
            await session.flush()
        sub = None
    if sub is None:
        sub = Subscription(org_id=org_id, plan_code=plan_code, status="active", provider=provider,
                           provider_ref=provider_ref, period_start=now, period_end=now + timedelta(days=days),
                           auto_renew=auto_renew)
        session.add(sub)
    await session.flush()
    await audit.record(session, "billing.subscription_activated", actor_id=None, org_id=org_id,
                       target_type="subscription", target_id=sub.id,
                       metadata={"plan": plan_code, "period_end": sub.period_end.isoformat(), "provider": provider})
    return sub


async def cancel(session: AsyncSession, *, org_id: uuid.UUID) -> Subscription | None:
    """Stop renewal. Access continues until period_end."""
    sub = (await session.execute(select(Subscription).where(
        Subscription.org_id == org_id, Subscription.status.in_(("active", "past_due"))))).scalar_one_or_none()
    if sub is None:
        return None
    sub.status, sub.auto_renew = "cancelled", False
    await session.flush()
    await audit.record(session, "billing.subscription_cancelled", actor_id=None, org_id=org_id,
                       target_type="subscription", target_id=sub.id)
    return sub


async def expire_due(session: AsyncSession, now: datetime | None = None) -> int:
    """Scheduled job: mark subscriptions whose paid access has ended as expired."""
    now = now or datetime.now(UTC)
    subs = (await session.execute(select(Subscription).where(
        Subscription.status.in_(("active", "past_due", "cancelled")), Subscription.period_end <= now))).scalars().all()
    n = 0
    for sub in subs:
        if sub.status == "past_due" and sub.grace_until and sub.grace_until > now:
            continue
        sub.status = "expired"
        n += 1
        await audit.record(session, "billing.subscription_expired", actor_id=None, org_id=sub.org_id,
                           target_type="subscription", target_id=sub.id)
    await session.flush()
    return n
