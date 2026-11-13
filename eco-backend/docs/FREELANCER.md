# Freelancer Growth division

For freelancers, remote workers and independent professionals anywhere, with deliberate support for African
professionals. One **private workspace per person**, always in their personal organisation (teams can't see it),
holding a reusable professional profile that powers every tool.

- Backend: `app/api/v1/freelancer.py`, `app/services/freelancer.py` (countries, conventions, eligibility,
  time-zone overlap, rate floor, red flags, checked resource directory), `app/ai/agents/freelancer.py` (10 agents),
  `app/schemas/freelancer.py`, typed profile in `app/schemas/common.py`, migration `0006_freelancer`
- Web app: `eco-web/src/app/freelancer/onboarding`, `eco-web/src/app/f/[ws]/*`, `src/components/fl/*`
- Tests: `tests/ai/agents/test_20…29` (one per agent, run one at a time), `tests/freelancer/` (13 workflow tests),
  `eco-web/e2e/freelancer.mjs` (14 browser workflows)

## Career stages
`beginner` (skilled, no clients yet) · `experienced_freelancer` · `job_seeker` (remote jobs) · `consultant`.
The stage changes the dashboard's recommended steps (e.g. beginners: starter offer → first case study →
outreach; job seekers: tailored CV → opportunities → interview practice) and the guidance given to every agent.

## What works today, and what needs an integration
Served by `GET /v1/freelancer/capabilities` and shown on Settings.

| Feature | Status | How it works now |
|---|---|---|
| Professional profile & skills assessment | **Works now** | Profile from a 6-step onboarding; the AI assessment marks each skill *shown* (backed by experience/portfolio/certificate refs), *listed* (only named) or *suggested* (to learn). The user applies and edits it |
| CV & resume builder, job-tailored | **Works now** | Built only from profile entries (each line cites its ref; titles/employers must match). Pasted job posts decide emphasis; their keywords split into *matched* (the profile supports them) and *missing* (never added). Conventions for 7 target markets |
| Proposals, applications & cover letters | **Works now** | Every claim cites the profile or the user's own words. Job posts are sent as untrusted external data, so they can never count as the user's experience |
| Interview prep & mock interviews | **Works now** | Likely questions, outlines, STAR stories from real entries; practice sessions score typed answers (structure, relevance, specificity, clarity) and show a stronger version with no new facts |
| Portfolio & case studies | **Works now** | Results only if given, otherwise `[ADD RESULT]`; client named only if the user named it; testimonials only if pasted verbatim |
| Personal branding & content | **Works now** | Bios (X bio ≤160 chars) and post drafts for chosen platforms. Nothing is posted |
| Client acquisition & outreach prep | **Works now** | Ideal-client segments, research checklist, message drafts with placeholders. Only prospects the user named; nothing is sent |
| Service packaging & pricing | **Works now** | Every price labelled by basis: *your rates*, *meets your income goal* (≥ the computed floor) or *suggested starting point: test it*. User's currencies only. Cross-border payment checks, no provider claims |
| Learning plans | **Works now** | Exact number of weeks with a portfolio output each week; links only from the checked directory |
| Application tracker, saved work, files | **Works now** | Statuses with history, next steps and due dates, linked CV/letter, projects, versions, exports (Markdown, HTML, plain text), uploaded files |
| Opportunity checks | **Works with your data** | For listings the user adds: eligibility from what the listing states, time-zone overlap for today's date (DST-aware), scam-signal detection, deadline expiry, and "verified by you" only after the user checks the source |
| Remote job discovery | **Works with your data** | A directory of job boards, marketplaces, payment and learning resources, each checked on 2026-11-12 with its source. No live job feed |
| Live job feeds / auto-apply | **Needs integration** | Not connected; nothing is submitted |
| Sending outreach / posting content | **Needs integration** | Not connected |
| Currency conversion | **Needs integration** | No exchange-rate feed; amounts stay in their own currency |

### Integrations still to build
Check each provider's current API terms before building. [Medium confidence: access rules change.]
- **Job feeds** (job board or aggregator APIs, ATS feeds): import listings as `source=integration`, still subject
  to eligibility/red-flag checks and expiry.
- **Exchange rates**: a rates provider with a timestamp on every conversion.
- **Live research provider**: lets the researcher agent cite current company or market facts (the interface exists).
- **Calendar/email**: for interview reminders and follow-ups (approval required before anything is sent).

## Global and African support
- **89 countries** (all 54 African countries plus major hiring markets) with a suggested currency and IANA time
  zone. Both are editable; several countries span zones or use more than one currency.
- **Multi-currency**: profile, rates, goals, services and listings each carry their own ISO currency. The AI may
  price only in currencies the user gave.
- **Time zones**: overlap between a listing's required hours (in its zone) and the user's working window,
  computed for a real date so daylight saving is reflected (e.g. New York 9–17 → 15:00–23:00 in Lagos in winter).
- **Eligibility**: from country codes or region tokens the listing states (WORLDWIDE, AFRICA, EMEA, EU, LATAM,
  APAC…). It's *unclear* when the listing doesn't say, never guessed.
- **Application conventions**: international remote, US, Canada, UK, continental Europe, Gulf, and local African
  roles. These are general norms (length, photo, personal details, paper size); the employer's instructions win.
  [Medium confidence: conventions vary by employer.]
- **Getting paid**: users record the payment methods they can actually use; agents are told not to assume any
  provider works in their country. The directory lists Payoneer, Wise, Grey, Raenest (formerly Geegpay) and
  Chipper Cash with checked sources and a "confirm for your country" note.
- **Mobile and lightweight**: phone-first layouts with a bottom navigation (checked for no sideways scroll), short
  forms, plain-text export for pasting into application forms, and free, low-bandwidth learning resources preferred.

### Resource directory sources (checked 2026-11-12)
- Remote boards and marketplaces: [Pulse Nigeria, June 2026](https://www.pulse.ng/story/best-platforms-foreign-remote-jobs-nigeria-2026061013113481896)
- Remote Africa: [remoteafrica.io/about-us](https://remoteafrica.io/about-us)
- Payment options: [Grey blog, updated Oct 2026](https://grey.co/blog/foreign-account-options-for-africans-working-online),
  [TechCabal on Raenest, Nov 2025](https://techcabal.com/2025/11/04/raenest-zero-deposit-fees/)
- ALX Africa: [ALX FAQ](https://www.alxafrica.com/frequently-asked-questions)

## Honesty rules (enforced in code, tested)
- Experience, employers, dates, qualifications, certifications, results, numbers and testimonials come only from
  the profile (cited `profile:…` refs) or the user's own words. External text (job posts, listings) reaches the
  model inside `<untrusted_data>` boundaries via `RunRequest.external`, and is excluded from the "user's words".
- Small but important numbers are checked too: "5 years of experience" is rejected unless the 5 is in the profile.
- The AI skills assessment is never fed back as evidence (`get_profile` excludes it).
- Opportunity analysis may not recommend a plain "apply" when the computed eligibility is `not_eligible` or red
  flags exist, and must always list what to verify at the source.
- Nothing is sent, posted, submitted or paid; "Applied" is the user's own record.

## API (all under `/v1`; full list in `openapi.json`)
| Method | Path | Notes |
|---|---|---|
| GET / POST | /freelancer/onboarding | State / create the personal workspace with the profile (409 if it exists) |
| GET | /freelancer/reference, /freelancer/capabilities | Countries, currencies, stages, conventions, resource directory; feature matrix |
| POST | /freelancer/rate-floor | Minimum hourly/daily rate from the user's income goal, hours, costs, billable share and tax |
| GET / PUT | /workspaces/{id}/professional-profile | The typed profile (shared profiles API) |
| GET | /workspaces/{id}/freelancer/overview | Dashboard |
| PUT | …/freelancer/assessment | Edit the assessment |
| POST | …/freelancer/generate | `{tool, brief, job_text?, opportunity_id?, application_id?, target_role?, market?, letter_type?, platforms?, weeks?, hours_per_week?, question_count?}` |
| POST | …/freelancer/runs/{run_id}/save, /apply-assessment | Save as a versioned item (optionally into a project) / apply |
| GET, PATCH, GET | …/freelancer/work, /work/{id}/project, /work/{id}/export?format=md\|html\|txt | Saved work |
| GET / POST / GET / PATCH / DELETE | …/freelancer/opportunities[/{id}] | Each returns `checks` (eligibility, timezone, risk_signals, deadline, verified) |
| POST | …/opportunities/{id}/verify, /track | User confirms at the source (open/closed) / start an application |
| GET / POST / PATCH / DELETE | …/freelancer/applications[/{id}] | Status changes append to `history` |
| GET / POST / GET | …/freelancer/interviews[/{id}] | Practice sessions from a prep run or own questions |
| POST | …/interviews/{id}/answers, /complete | Score one answer (one AI generation) / finish |

## Plan note
A Free plan allows one workspace per organisation, so a Free user who already has a Creator or Business workspace
in their personal organisation needs to upgrade to add Freelancer Growth. Onboarding shows this before they start.
