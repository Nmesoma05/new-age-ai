"""Manually activate or extend a paid plan (beta users paying by invoice, until Paystack checkout ships).

    python -m scripts.activate_plan --org <org-uuid> --plan pro --days 30 --ref INV-2026-014 --by "Stephen"

Writes the same subscription records the payment webhook would, with provider "manual" and your invoice reference,
plus an audit event naming who did it. Run from the host's shell on the API service (it uses the app's settings).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from app.core.db import transaction
from app.services import audit, subscriptions


async def main(org: str, plan: str, days: int, ref: str, by: str) -> int:
    async with transaction(None, context="system") as s:
        sub = await subscriptions.activate_period(s, org_id=uuid.UUID(org), plan_code=plan, provider="manual",
                                                  provider_ref=ref, days=days, auto_renew=False)
        await audit.record(s, "billing.manual_activation", actor_id=None, org_id=uuid.UUID(org),
                           target_type="subscription", target_id=sub.id,
                           metadata={"plan": plan, "days": days, "ref": ref, "by": by})
        print(f"{plan} active for org {org} until {sub.period_end:%Y-%m-%d %H:%M} UTC (ref {ref})")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", required=True)
    ap.add_argument("--plan", required=True, choices=sorted(subscriptions.PAID_PLANS))
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--ref", required=True, help="invoice or payment reference")
    ap.add_argument("--by", required=True, help="who is activating it (goes in the audit log)")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.org, a.plan, a.days, a.ref, a.by)))
