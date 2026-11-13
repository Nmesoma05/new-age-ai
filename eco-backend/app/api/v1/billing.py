import hashlib
import hmac
import json
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import system_context
from app.core.deps import OrgCtx, get_session, org_ctx
from app.core.errors import AppError
from app.models import WebhookEvent
from app.schemas.common import SubscriptionOut, UsageOut
from app.services import billing, subscriptions

router = APIRouter(prefix="/v1", tags=["billing"])


@router.get("/orgs/{org_id}/subscription", response_model=SubscriptionOut)
async def get_subscription(ctx: OrgCtx = Depends(org_ctx)):
    ctx.require("org.billing.read")
    ent = await billing.entitlements(ctx.principal.session, ctx.org.id)
    sub = ent.subscription
    return SubscriptionOut(plan=ent.plan.code, plan_name=ent.plan.name, ai_unlimited=ent.plan.ai_unlimited,
                           status=sub.status if sub else "free", period_end=sub.period_end if sub else None,
                           auto_renew=sub.auto_renew if sub else None, max_workspaces=ent.plan.max_workspaces,
                           max_seats=ent.plan.max_seats)


@router.get("/orgs/{org_id}/usage", response_model=UsageOut)
async def get_usage(ctx: OrgCtx = Depends(org_ctx)):
    """Paid plans report no counts: usage is unlimited while the plan is active."""
    ctx.require("org.read")
    s = ctx.principal.session
    ent = await billing.entitlements(s, ctx.org.id)
    if ent.plan.ai_unlimited:
        return UsageOut(plan=ent.plan.code, ai_unlimited=True, free_monthly_limit=None, free_used_this_month=None,
                        free_remaining=None)
    used = await billing.free_used(s, ctx.org.id)
    limit = ent.plan.free_monthly_limit or 0
    return UsageOut(plan=ent.plan.code, ai_unlimited=False, free_monthly_limit=limit, free_used_this_month=used,
                    free_remaining=max(0, limit - used))


@router.post("/webhooks/paystack", status_code=200, include_in_schema=False)
async def paystack_webhook(request: Request, session: AsyncSession = Depends(get_session)):
    """Verify, store raw, then apply. Signature: HMAC-SHA512 of the raw body with the secret key,
    sent as `x-paystack-signature` (confirm against Paystack's current docs in the payments spike).

    Event mapping is intentionally narrow until the spike confirms payload shapes:
      charge.success with metadata {org_id, plan_code, period_days} -> activate or extend a prepaid period
      subscription.disable with metadata {org_id}                    -> cancel (access continues to period end)
    """
    secret = get_settings().paystack_secret_key
    raw = await request.body()
    sig = request.headers.get("x-paystack-signature", "")
    if secret is None:
        raise AppError(503, "webhooks_not_configured", "Not configured")
    expected = hmac.new(secret.get_secret_value().encode(), raw, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise AppError(401, "invalid_signature", "Invalid signature")
    try:
        payload = json.loads(raw)
        event = payload["event"]
        data = payload.get("data") or {}
        event_id = f"{event}:{data.get('reference') or data.get('id')}"
    except (ValueError, KeyError, TypeError):
        raise AppError(400, "invalid_payload", "Invalid payload") from None

    async with system_context(session):
        res = await session.execute(insert(WebhookEvent).values(provider="paystack", event_id=event_id, payload=payload)
                                    .on_conflict_do_nothing().returning(WebhookEvent.id))
        if res.scalar_one_or_none() is None:
            return {"status": "duplicate"}  # already processed: idempotent
        meta = data.get("metadata") or {}
        try:
            org_id = uuid.UUID(str(meta.get("org_id")))
        except ValueError:
            return {"status": "ignored"}
        if event == "charge.success" and meta.get("plan_code"):
            await subscriptions.activate_period(session, org_id=org_id, plan_code=str(meta["plan_code"]),
                                                provider="paystack", provider_ref=str(data.get("reference")),
                                                days=int(meta.get("period_days", 30)),
                                                auto_renew=bool(data.get("authorization", {}).get("reusable", False)))
        elif event == "subscription.disable":
            await subscriptions.cancel(session, org_id=org_id)
        else:
            return {"status": "ignored"}
        await session.execute(update(WebhookEvent).where(WebhookEvent.provider == "paystack",
                                                         WebhookEvent.event_id == event_id).values(processed_at=func.now()))
    return {"status": "processed"}
