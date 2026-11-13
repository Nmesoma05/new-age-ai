# Incident response

## Severity
| Level | Examples | Response | Update users |
|---|---|---|---|
| SEV1 | Site down; data exposed to the wrong tenant; payments charging wrongly; data loss | Page on-call now; founder informed within 15 min | Status page within 30 min, then hourly |
| SEV2 | A core flow broken (sign-in, AI drafting, uploads, exports) for many users; AI paused by budget | On-call within 30 min | Status page within 1 h |
| SEV3 | One feature degraded, a workaround exists | Next working day | In the ticket |

## First 15 minutes
1. Acknowledge the alert; open a thread in #incidents: what you see, since when, who's leading.
2. Check: last deploy (roll back first if it was in the last 2 hours: see deploy-and-rollback.md), `/ready`, error tracking, host status, AI provider status, Paystack status.
3. Mitigate before diagnosing: roll back, scale up, toggle `OUTBOUND_HTTP_ENABLED=false` (stops all integrations), raise or lower `AI_DAILY_BUDGET_USD`, maintenance mode.
4. Post a status update even if you only know the symptom.

## Personal data breach (Nigeria Data Protection Act 2023)
1. Contain (revoke keys, disable the route, roll back). Preserve logs; don't delete evidence.
2. Founder + DPO decide within 24 h whether it risks people's rights. If yes: **notify the NDPC within 72 hours** of becoming aware (phased if facts are incomplete), and tell affected users **immediately** where the risk is high, with what they should do.
3. Record: what, when found, who/what affected, actions, notifications sent. Keep the record even if you decide not to notify.

## After every SEV1/SEV2
Blameless review within 5 working days: timeline, cause, what detected it, what slowed us, actions with owners and dates.

## Contacts (fill in)
On-call rota · founder · DPO · lawyer · host support · AI provider support · Paystack support · email provider support.
