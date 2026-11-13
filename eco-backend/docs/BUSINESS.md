# Business Marketing division

For entrepreneurs, startups, SMEs and established businesses in any industry or country. One account; one
**workspace per business**, each with its own profile, Marketing Intelligence Profile, saved work, campaigns,
approvals and results. Nothing is shared between businesses.

- Backend: `app/api/v1/business.py`, `app/services/business.py` (category playbooks, maths, CSV),
  `app/ai/agents/business.py` (7 agents), `app/schemas/business.py`, migration `0005_business`
- Web app: `eco-web/src/app/business/onboarding`, `eco-web/src/app/businesses`, `eco-web/src/app/b/[ws]/*`
- Tests: `tests/ai/agents/test_13…19` (one per agent), `tests/business/` (16 workflow tests),
  `eco-web/e2e/business.mjs` (13 browser workflows)

## What works today, and what needs an integration

Served by `GET /v1/business/capabilities` and shown on each business's Settings page.

| Feature | Status | How it works now |
|---|---|---|
| AI marketing strategist (chat) | **Works now** | Uses only this business's profile, saved work, memory and uploaded documents |
| Marketing Intelligence Profile | **Works now** | Built by the AI from the onboarding answers; applied only when you choose; every section editable |
| Positioning, brand identity & messaging | **Works now** | Positioning, value proposition, pitch, personality, tone, messages, taglines, visual direction (in words). You pick which parts to apply to the profile |
| Marketing plan generator | **Works now** | 1–12 months; objectives with your targets (or `[TARGET]`), channel plan, one timeline entry per month, split of *your* budget, KPIs |
| Content & social strategy (AIDA) | **Works now** | Attention → Interest → Desire → Action with draft posts per platform |
| Advertising & campaign planning | **Works now** (planning) | Readiness check, platforms, targeting ideas, ad copy, test plan, compliance checks; becomes a trackable campaign |
| Lead generation & acquisition | **Works now** | Funnel stages, tactics, hooks, quick wins, measures |
| Customer retention | **Works now** | Same structure, focused on keeping customers |
| Projects & saved work | **Works now** | Save any output into a project; edit (new version each save); restore versions; export Markdown/HTML |
| Market & customer research | **Works with your data** | From your profile, notes and documents; every insight cites its basis. No live market data or web research is connected |
| Competitor analysis | **Works with your data** | Only competitors you named, using what you observed. It can't see their accounts, prices or ads |
| Performance analysis & reports | **Works with your data** | Results you enter or upload by CSV; the app does the maths; the AI may only use those numbers; export CSV/Markdown/HTML |
| Launching ads / spending budget | **Needs integration** | You can request approval to spend. Approval is recorded, but nothing is launched or paid (`409 no_executor`) |
| Sending email / SMS / WhatsApp broadcasts | **Needs integration** | Can be requested for approval; nothing is sent |
| Automatic results import (ads, CRM, analytics, POS) | **Needs integration** | No ad platform, CRM, analytics or sales system is connected; nothing is fetched or estimated |

### Third-party integrations still to build
Each is a separate project. Capabilities below are what I believe these platforms offer; **verify against their
current API docs and access requirements before building** [Medium confidence — APIs, approval processes and
permissions change].
- **Ad platforms** (Meta Marketing API, Google Ads API, TikTok/LinkedIn ads): launch/pause campaigns and read spend
  and conversions. Usually need developer access approval, OAuth per ad account and business verification.
  Would register an executor for `spend_money` and an importer writing `marketing_results` with `source=integration`.
- **Messaging** (email service provider, SMS gateway, WhatsApp Business Platform): executor for `send_message`.
  WhatsApp broadcasts have template and opt-in rules.
- **CRM / sales / analytics** (e.g. HubSpot, POS systems, Google Analytics): import leads, customers and revenue.
- **Web research provider**: live market and competitor data with citations (the engine already has a research
  interface; no provider is configured).

## How advice adapts to the business
- **16 category playbooks** (`services/business.py: CATEGORIES`): typical focus, often-useful channels, useful
  measures and cautions (e.g. health claims, financial promotions).
- **4 stages** (idea, new, growing, established) with stage guidance; e.g. idea-stage businesses are steered to
  validate demand before spending.
- Every tool request starts with a "Business context" block: category, stage, model (B2C/B2B), location, target
  markets, budget in the local currency, channels in use, then the playbook marked *general guidance, use only where
  it fits*. The agents' rules say the profile and the owner's words win.
- The dashboard's **Recommended next** list is deterministic (`next_steps`) and depends on stage, category, model,
  what's saved and whether results exist (e.g. B2B → lead generation; consumer brands → AIDA content).

## Rules that keep it honest
- No invented figures: money and percentages must appear in the inputs (`no_invented_numbers`); positioning copy may
  not contain *any* number that isn't in the profile ("trusted by 500 families" is rejected); the performance
  analyst may only use numbers in the recorded results (`strict_numbers`).
- Competitors: only those the owner named. Research claims: no "web research" when none happened.
- Requested shape is enforced: plan length = months asked and one timeline entry per month; ad dates = the dates
  asked; ad copy only for platforms in the plan; AIDA stages in order; focus = the tool used.
- Results maths never adds different currencies; figures nobody recorded are `null` ("–"), never 0; every row
  keeps its `source`; reports state that figures were entered by the team.
- External actions are only `pending_actions`. Workspace admins decide; spending also needs an org owner/admin.

## Workflows (backend test + browser test)
1. Sign up → product chooser → 6-step onboarding (who, category & stage, basics, offers & customers, competitors
   & channels, goals & budget) → AI builds the Intelligence Profile → owner applies → edits and saves.
2. Dashboard adapts (stage/category-aware next steps, priorities, 30-day results, approvals waiting).
3. Strategy tools: positioning (apply chosen parts), market, competitors, plan, AIDA content, ads, acquisition,
   retention, report. Each runs in its own conversation so earlier outputs don't leak in.
4. Save to projects, edit (versions), export Markdown/HTML.
5. Ad plan → campaign; request approval to spend → approve returns "can't carry this out yet" → reject.
6. Results by hand or CSV (all-or-nothing validation, aliases like "Facebook Ads" → `meta_ads`), report with cost
   per lead, cost per customer, return on spend, lead→customer rate; AI analysis; exports.
7. Strategist chat; viewers can read but not run AI or write; wrong-product and cross-business access refused.

## API (all under `/v1`; problem+json errors; workspace roles enforced; full list in `openapi.json`)
| Method | Path | Notes |
|---|---|---|
| GET / POST | /business/onboarding | State / complete (`mode: solo\|team`, `profile`) |
| GET / POST | /business/businesses | List / add (org owner/admin; plan workspace limit applies) |
| GET | /business/categories, /business/capabilities | Playbooks, stages, channels; feature status matrix |
| GET / PUT | /workspaces/{id}/business-profile | Business facts (shared profiles API) |
| GET | /workspaces/{id}/business/overview | Dashboard |
| PUT | /workspaces/{id}/business/intelligence | Edit the Intelligence Profile |
| POST | /workspaces/{id}/business/generate | `{tool, brief, plan_months?, platforms?, start_date?, end_date?, document_ids?}` |
| POST | /workspaces/{id}/business/runs/{run_id}/save | `{title?, project_id?}` → versioned asset |
| POST | …/runs/{run_id}/apply-intelligence, /apply-positioning, /create-campaign | Explicit apply steps |
| POST | /workspaces/{id}/business/approvals | `spend_money` (amount + currency) or `send_message` (email/sms/whatsapp) |
| GET | /workspaces/{id}/business/work | `?project_id=&type=&unfiled=` |
| PATCH | …/business/work/{asset_id}/project | Move between projects |
| GET | …/business/work/{asset_id}/export | `?format=md\|html` |
| GET / POST / GET / PATCH / DELETE | …/business/campaigns[/{id}] | Detail includes linked results summary |
| GET / POST / DELETE | …/business/results[/{id}] | Manual results |
| POST | …/business/results/import | CSV (multipart `file`, optional `currency`, `campaign_id`) |
| GET | …/business/report, /report/export | `?start&end`; export `format=csv\|md\|html`, `run_id` adds the AI analysis |

Approve/reject use the shared `/workspaces/{id}/actions/{action_id}/approve|reject`.
