# Creator & Marketing division

For content creators, social media managers, digital marketers, brand strategists, freelance marketers and
agencies. One account; one **workspace per client**, each with its own business information, brand voice,
audience, platforms, goals, competitors, content, calendar, campaigns, approvals and reports.

- Backend: `app/api/v1/creator.py`, `app/services/creator.py`, `app/ai/agents/creator.py`, migration `0004_creator`
- Web app: `eco-web/` (Next.js 15). Its README covers setup and the browser test.
- Tests: `tests/creator/` (21 workflow tests), `tests/ai/agents/test_08…12` (one per new agent),
  `eco-web/e2e/run.mjs` (16 browser workflows)

## What works today, and what needs an integration

The same matrix is served by `GET /v1/creator/capabilities` and shown on each client's Settings page, so the
app never implies more than it does.

| Feature | Status | How it works now |
|---|---|---|
| AI social media assistant | **Works now** | Chat that uses only this client's profile, memory and documents; can read uploaded briefs |
| Content & copywriting studio | **Works now** | Posts, threads, captions, scripts per platform; every draft is editable before and after saving, with version history |
| Brand strategy & voice profiles | **Works now** | Structured profile (business, offers, audience and personas, goals, competitors, pillars, voice); the AI proposes and you choose which parts to apply |
| Social strategy & content calendars | **Works now** | Month grid, agenda on phones, AI plan for a date range you import selectively, CSV and iCalendar export |
| Campaign planning | **Works now** | Campaigns with phases, channels, deliverables, KPIs and budget notes; AI plan → campaign; calendar items link to campaigns |
| Multi-client workspaces | **Works now** | Solo (personal) or agency (team org); client switcher; plan limits on the number of clients; strict data separation |
| Organisation & approval workflows | **Works now** | Library with statuses; send for approval → comment → request changes → approve (workspace admin); client review links (no account needed, expiring, revocable, comments-only option) |
| Exports | **Works now** | Library (CSV, Markdown), calendar (CSV, .ics), report (CSV, Markdown, HTML; with AI commentary if generated) |
| Audience & competitor research | **Works with your data** | Analyses the notes you record and documents you upload; every insight cites its source. Live web research needs a research provider (not connected) |
| Performance reporting & analytics | **Works with your data** | Figures entered by hand or uploaded as CSV from each platform's insights; totals, engagement rate, platform breakdown, top posts, follower change; AI commentary uses only those numbers |
| Publishing / scheduling to platforms | **Needs integration** | Nothing is posted. You post approved content yourself, then "Mark as posted" (optionally with the live link); linked content must be approved first |
| Automatic analytics import | **Needs integration** | No platform API is called; no figures are fetched or estimated |
| Inbox / comment and DM replies | **Needs integration** | Not available |

### Rules that keep the product honest
- "Posted" in the calendar means **a person said they posted it**; the record says so and isn't checked against the platform.
- Report figures carry their source (`manual`, `csv_import`). Figures that nobody recorded show as "–", never as 0.
- The report writer agent rejects any number that isn't in the recorded data; the research agent rejects competitors
  that weren't named and claims of web research that didn't happen.
- AI output never says something was posted, sent or paid (validator), and external actions can only be *proposed* for approval.

## Workflows (each is covered by a backend test and a browser test)

1. **Onboarding:** sign up → solo or agency → first client (name, industry, website, description, platforms) →
   audience, goal, voice → dashboard with a setup checklist.
2. **Brand:** edit the profile; "Build voice with AI" → review → apply selected parts (voice, positioning, personas, pillars).
3. **Studio:** brief + platforms + number of drafts → editable draft cards with character counters → save chosen
   drafts (edits become version 2, so the AI original stays in the history).
4. **Library & approvals:** edit, view or restore versions, comment, send for approval, approve (admin) or request
   changes (with comment); share a client review link; the client approves or asks for changes by name; the team sees it in the history.
5. **Calendar:** plan with AI → import chosen slots (optionally into a campaign) → link content → mark as posted after posting it yourself.
6. **Campaigns:** plan with AI → create campaign → phases timeline, deliverables, KPIs, linked calendar.
7. **Reports:** add figures or upload CSV (all-or-nothing, every bad row listed) → followers → summary → AI commentary → export.
8. **Multi-client:** add clients (Free allows one; paid plans more); switch between clients; data never crosses.

## API (all under `/v1`, problem+json errors, workspace roles enforced; full list in `openapi.json`)

| Area | Endpoints |
|---|---|
| Onboarding & clients | `GET/POST /creator/onboarding`, `GET/POST /creator/clients`, `GET /creator/capabilities` |
| Dashboard | `GET /workspaces/{id}/creator/overview` |
| Studio | `POST …/creator/generate` (`kind`: content, brand_voice, calendar, campaign, research, report); `POST …/creator/runs/{run}/save-drafts`, `/apply-brand`, `/import-calendar`, `/create-campaign` |
| Calendar | `GET/POST …/creator/calendar`, `PATCH/DELETE …/calendar/{id}`, `POST …/calendar/{id}/mark-published`, `GET …/calendar/export?format=csv\|ics` |
| Campaigns | `GET/POST …/creator/campaigns`, `GET/PATCH/DELETE …/campaigns/{id}` |
| Approvals | `GET …/creator/approvals`, `POST …/creator/assets/{id}/submit`, `/decision`, `GET/POST …/assets/{id}/comments`, `GET/POST …/creator/review-links`, `DELETE …/review-links/{id}` |
| Client review (no account) | `GET /review/{token}`, `POST /review/{token}/assets/{asset}` |
| Performance | `GET/POST …/creator/metrics`, `DELETE …/metrics/{id}`, `POST …/metrics/import` (CSV), `GET/PUT …/creator/followers`, `GET …/creator/report`, `GET …/creator/report/export?format=csv\|md\|html` |
| Library export | `GET …/creator/library/export?format=csv\|md` |

Profile: `GET/PUT /workspaces/{id}/client-account` now also takes `website`, `business_info`, `audience`, `goals`,
`competitors`, `content_pillars` (all validated).

## New agents (built and tested one at a time)

| Agent | Output | Code-enforced checks |
|---|---|---|
| `creator.brand_strategist` | Positioning, voice traits, tone by platform, words to use/avoid, sample lines, personas, pillars | No invented statistics; at least 2 traits and 2 pillars |
| `creator.calendar_planner` | Strategy, rhythm, dated slots | Exactly the requested period and platforms; valid dates and 24h times |
| `creator.campaign_planner` | Objective, phases, channels, deliverables, KPIs, budget, risks | Exactly the requested dates; phases inside them; deliverables only on plan channels; no invented prices or targets |
| `creator.research_analyst` | Audience and competitor insights, gaps, actions | Every insight cites a profile/doc ref, search URL or the user's message; only named competitors; no false web-research claims |
| `creator.report_writer` | Headline, highlights, improvements, next actions, caveats | Every number must appear in the recorded data; caveats required |

## Incomplete integrations and next steps

| Gap | What's needed | Notes |
|---|---|---|
| Publishing (Instagram/Facebook, X, LinkedIn, TikTok, YouTube, Threads, Pinterest, WhatsApp) | One executor per platform via the approval-gated `pending_actions` flow | Each platform has its own app review, permissions, rate limits and pricing. Verify each platform's current API and terms before building |
| Analytics import | Per-platform insight readers writing `post_metrics` with `source = 'integration'` | The data model already distinguishes the source |
| Web research | A `ResearchBackend` (search API) | Choose a provider; check terms and pricing |
| Paid upgrade checkout | Paystack transaction initialisation and a billing page | The webhook that activates plans exists; there's no in-app checkout yet, so the app says to contact support |
| Invitations | Email invites for team members | Today an existing user is added by email (org) and then to a client |
| Background jobs | Celery for ingestion, summaries, subscription expiry, overdue-post reminders | All run inline today |
| Scheduling reminders | Notifications (email/push) for upcoming and overdue posts | Not built |
| Image/video creation | Not in scope; the studio describes visuals rather than generating them | |
