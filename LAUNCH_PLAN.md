# Launch readiness plan

New Age AI, a product of New Age Media: Creator & Marketing, Business Marketing, Freelancer Growth. Prepared 13 Nov 2026.

## Verdict

**Not ready for a public launch today. Ready to set up staging and run a closed, free beta in about 2–3 weeks, once the owner actions below are done.**

The code is launch-shaped. Containers, pipelines, health checks, backups, cost caps and data-rights features are built, and everything that could run here was tested. A full staging rehearsal passed 17 of 18 smoke checks; the 18th (real AI) needs internet and an API key.

What blocks a public launch is mostly outside the code:

1. **Legal.** The privacy policy and terms are drafts. They need a Nigerian data-protection lawyer, plus registration and DPO decisions under the Nigeria Data Protection Act. The production pipeline refuses to deploy while they're drafts.
2. **Paid plans can't be bought yet.** Paystack checkout isn't built. Only the signed webhook receiver exists, and its signature scheme now matches Paystack's docs. Plans can be activated manually for beta users.
3. **Accounts and keys to create:** domain, host, AI provider project, email provider, error tracking, Paystack live keys.
4. **Things only a real staging environment can prove:**
    - real AI quality and latency;
    - real ClamAV scanning;
    - creating the restricted database role on the managed host;
    - the deploy-hook format;
    - real client IPs behind the host's proxy.

A staging rehearsal here caught a **critical bug** before launch: the virus-scanner check would have rejected every file upload in production. It's fixed and covered by tests.

## What was built and verified this round

| Area | What exists now | How it was verified |
|---|---|---|
| Environments | `ENV=staging` gets every production guard. The app refuses to start with: a Paystack test key in prod or a live key in staging; local file storage; the dev email outbox; non-https URLs; no AI daily budget; **$0 AI prices** (which would silently disable every cost cap); unapproved legal version; scanning off | 16 config tests |
| Health | `/health` (liveness, reports the release) and `/ready` (database, schema at migration head, storage read/write, scanner) | Tests; staging rehearsal |
| Logs and errors | JSON logs with request ID, release and env. No query strings, bodies or secrets. Optional Sentry with no personal data. AI provider failures logged as errors | Tests; rehearsal logs checked for secrets: none |
| AI cost | Platform-wide daily spend cap (`AI_DAILY_BUDGET_USD`): warning at 80%, generations pause at 100% until midnight UTC | Test |
| Data rights | Download my data (JSON); Delete my account (immediate anonymisation, workspaces erased with files after 30 days by a daily purge job); terms acceptance recorded at sign-up | 9 backend tests + 3 browser steps |
| Legal pages | `/privacy` and `/terms` drafted from what the app really does, shown with a "Draft for legal review" banner. Release gate blocks production while drafts or placeholders remain | Browser test; gate run (correctly fails today) |
| Email | SMTP sender (any provider), STARTTLS required, reset links never stored | Tests |
| Rate limits | Per-IP sign-in, sign-up and reset limits moved into Postgres, so they hold across workers and servers | Test with two app instances |
| Containers | API and web Dockerfiles, non-root, health checks. Postgres 16 client tools in the API image for backups | hadolint clean. Image build **blocked here** (registry unreachable); CI builds and scans them |
| CI/CD | GitHub Actions: CI (tests, browser suites, audits, image scan), auto-deploy to staging plus smoke test, manual production promotion with approval, gates and automatic rollback | actionlint clean; deploy scripts tested against a fake hook |
| Infrastructure as code | Render blueprints for staging and production | Field names checked against Render's spec |
| Database safety | Pre-deploy step: migration safety gate → backup → migrate. Gate blocks destructive migrations unless approved | Gate tested both ways; backup + migrate run on staging DB |
| Backups | Daily logical backup with manifest; monthly restore drill into a scratch database | Backup to S3-compatible storage + drill passed twice |
| Rollback | Previous release runs on the new schema | Rehearsed: sign-up, workspace, sign-in OK |
| Smoke test | `scripts/smoke.py`: staging journey (sign-up → workspace → AI → upload/download → export → delete) or production read-only checks | Rehearsal: 17/18 (AI blocked) |
| Bugs fixed | BUG-15 (Critical): scanner reply parsing rejected every clean upload. Also: missing request IDs in logs; AI failures not logged; terms checkbox below the touch-target size | Regression tests |

**Final regression (13 Nov):**
- 332 backend tests passed; 1 skipped (live AI evals need a key).
- Browser: 76 of 76 steps across 5 suites, including 24 persona and accessibility checks.
- Cross-tenant sweep: 630 requests, 0 leaks.
- Lint and typecheck clean; 0 server errors during the runs.

All browser suites run on the standalone production server (the one the Docker image runs).

## Environments

| | Staging | Production |
|---|---|---|
| Purpose | Final check of every release; closed beta in phase 1 | Real customers |
| `ENV` | `staging` (all production guards) | `prod` |
| Domains | `staging.<domain>`, `api.staging.<domain>`; `noindex`; behind an allowlist | `app.<domain>`, `api.<domain>` |
| Database | Its own; synthetic data only, never a production copy | Its own; HA, point-in-time recovery |
| Files | Its own bucket | Its own bucket, versioning on |
| Secrets | Its own set; test keys only | Its own set; live keys; no value shared with staging |
| Paystack | `sk_test_…` (live key refused) | `sk_live_…` (test key refused) |
| AI | Separate provider project, small budget | Separate project, production budget |
| Deploys | Automatic after CI passes on `main` | Manual promotion of the staging-verified image, second-person approval |

## 1. Infrastructure and hosting

**Recommendation: Render, Frankfurt region, Docker images built by GitHub Actions.** Render supports pgvector, pg_trgm and citext ([extensions](https://render.com/docs/postgresql-extensions)). It has a pre-deploy command for migrations and Frankfurt as a region ([blueprint spec](https://render.com/docs/blueprint-spec)). PITR is 7 days on Pro workspaces ([Render](https://render.com/articles/postgres-features-that-matter-for-production-pitr-read-replicas-and-native-exten)). Render has no African region; Frankfurt is the closest of its five.

| Component | Staging | Production |
|---|---|---|
| API (`eco-api`) | 1 instance, `0.5c-512mb` | 2 instances, `2c-4g`, 2 workers each |
| Web (`eco-web`) | 1 × `0.5c-512mb` | 2 × `1c-2g` |
| Postgres 16 | `0.5c-1g`, 10 GB | `4c-16g`, 50 GB, high availability, private network only |
| Virus scanner (ClamAV) | private service `0.5c-1g` | private service `1c-2g` |
| Files | S3-compatible bucket (AWS S3 eu-central-1 or Cloudflare R2) | Same, separate bucket, versioning |
| Jobs | backup daily 02:15 UTC, purge daily, restore drill monthly | Same |

Sizes are starting points. Confirm them with the staging load test, and check prices on Render's pricing page; none are quoted here.

**Verify on day 1 of staging:**

1. Render Postgres must allow creating the restricted `eco_app` role (`scripts/create_roles.sql`). This is a **hard requirement**: the app connects as a non-owner role so row-level security applies. If it isn't allowed, use AWS RDS or Neon instead.
2. Deploy hooks accept an image URL (`ops/deploy.sh`).
3. Cron jobs can run from an image.
4. Pick an S3 provider that supports the server-side encryption header; `/ready` will fail if it doesn't.

**Later option:** AWS has a Lagos Local Zone (parent region Cape Town) ([AWS](https://docs.aws.amazon.com/local-zones/latest/ug/available-local-zones.html)). Which services run there isn't listed. Consider it when latency or data-residency needs justify the extra operations work.

## 2. Environment variables and secrets

- **Where secrets live:** Render environment groups (`eco-secrets`, `eco-staging-secrets`) and GitHub environment secrets. Never in git, images or the web bundle.
- **Checks:** CI fails on committed `.env` files. The app validates configuration at start-up and refuses unsafe combinations (see the table above).
- **Full list:** `eco-backend/.env.example` and `eco-web/.env.example`.
- **Rotation schedule:** `runbooks/secrets.md`.
- **Must be set in production:**
    - `ENV`, `RELEASE` (set by the pipeline);
    - both database URLs (app role and owner role kept separate);
    - `JWT_SECRET` (≥ 32 characters), `CREDENTIALS_ENCRYPTION_KEY`;
    - S3 bucket and keys, ClamAV host;
    - SMTP host/password and `EMAIL_FROM`;
    - `PUBLIC_WEB_URL`, `CORS_ORIGINS`, `TRUSTED_PROXIES`;
    - AI provider key, `AI_MODEL`, `AI_MODEL_PRICES`, `AI_DAILY_BUDGET_USD`;
    - `LEGAL_TERMS_VERSION`, `PAYSTACK_SECRET_KEY`, `SENTRY_DSN`;
    - backup bucket.
- **Web:** `API_URL`, `COOKIE_SECURE=true`, `TRUST_FORWARDED_FOR=true`, and `NOINDEX=true` on staging only.
- **Access:** two people have production access; 2FA everywhere (GitHub, Render, Paystack, AI provider, registrar, email provider).

## 3. Database migrations and backups

- **Every deploy runs `scripts.predeploy` in the new image before it takes traffic:**
    1. Read the live schema version.
    2. Migration safety gate: additive changes only, unless one revision is explicitly approved.
    3. Back up if migrations are pending.
    4. Migrate.

    If any step fails, the old release keeps serving.
- **Expand/contract rule:** removing or renaming things ships one release after the code stops using them. That keeps rollback safe.
- **Backups, in three layers:**
    1. Render PITR (7 days).
    2. Daily logical backup to a separate account's private, versioned bucket, kept 35 days, with a manifest of row counts.
    3. Bucket versioning for files.
- **Monthly restore drill** into a scratch database. It checks the checksum, schema, row counts, RLS and grants.
- **Targets:** RPO ≤ 5 minutes (PITR); RTO ≤ 4 hours.
- **Before launch:** rerun the drill on staging with production-like data volume to measure real restore time.

## 4–5. Domain, DNS, SSL

| Record | Points to | Notes |
|---|---|---|
| `app.<domain>` | Render web service | Custom domain on the service |
| `api.<domain>` | Render API service | Only the web server calls it; CORS limited to `app.<domain>` |
| `staging.`, `api.staging.` | Staging services | `noindex`, allowlist |
| `<domain>` | Marketing site or redirect to `app.` | |
| Mail (`mail.<domain>` or root) | Email provider | SPF, DKIM and DMARC (start `p=none`, move to `quarantine` after 2 weeks of clean reports) |
| CAA | Your host's certificate authority [verify which Render uses] | Prevents other CAs issuing certificates |

- **Registrar:** 2FA and registrar lock on. Keep DNS at a provider with an audit log, such as Cloudflare in DNS-only mode, so Render can issue certificates [verify Render's proxy guidance].
- **Certificates:** Render issues and renews them [verify].
- **App-side protections, already built:**
    - HSTS for one year (when `COOKIE_SECURE=true`);
    - http→https redirect, checked by the smoke test;
    - secure, httpOnly, SameSite cookies;
    - Content-Security-Policy with a per-request nonce;
    - no framing;
    - the database reachable only on the private network;
    - SMTP requires STARTTLS.
- **Paystack webhook:** `https://api.<domain>/v1/webhooks/paystack`. Paystack signs each event with HMAC-SHA512 of the payload using your secret key, and retries for 72 hours if you don't return 200 ([Paystack](https://paystack.com/docs/payments/webhooks/)). The IP allowlist wasn't on the page fetched; get it from Paystack's dashboard or docs.

## 6. CI/CD and deployment pipelines

**Repository layout:** one monorepo containing `eco-backend/`, `eco-web/`, `ops/`, `runbooks/` and `.github/workflows/`. The `eco-ops` folder supplies the last three.

1. **CI** (every pull request and push):
    - backend: lint, `pip-audit`, migration gate, 332 tests on real Postgres with RLS, OpenAPI drift check;
    - web: typecheck, `npm audit` on runtime dependencies, build;
    - five browser suites, the cross-tenant sweep, and a "no server errors" check;
    - on `main`: build both images, Trivy scan (fail on critical issues that have a fix), push to GHCR tagged with the commit SHA.
2. **Deploy staging** (automatic after CI on `main`): deploy that SHA → wait until the API reports it and is ready → full smoke test with real AI.
3. **Deploy production** (manual):
    1. Enter the SHA and a reason.
    2. Gates: the SHA passed staging; legal pages approved; no deploy freeze.
    3. A second person approves (GitHub environment reviewers).
    4. Deploy → wait → production smoke test → **automatic rollback** to the previous release if it fails.

**Rule: nothing reaches production that didn't pass CI and the staging smoke test as the same image.**

**Set up in GitHub:**
- environments `staging` and `production` (with required reviewers);
- secrets `RENDER_DEPLOY_HOOK_API`/`_WEB` per environment, plus `SMOKE_EMAIL`/`SMOKE_PASSWORD` for production;
- variables `DOMAIN` and `DEPLOY_FREEZE`;
- branch protection on `main` (CI required, one review).

## 7. Monitoring, logs and error tracking

| Signal | Tool | Alert when |
|---|---|---|
| Uptime | External checker (Better Stack, UptimeRobot or similar) on `/ready` and `app./login` every minute, from Europe and Africa | 2 failures in a row → page |
| Errors | Sentry (`SENTRY_DSN`), tagged with env and release | New issue in production; error rate > 1% for 5 min |
| Logs | Render logs → a log service (Better Stack, Datadog or similar); JSON with request IDs | `level=critical` (AI budget reached) → page; `ai run failed` with `provider_error` > 5 in 5 min → page; `email delivery failed` → ticket |
| AI spend | App log at 80% and 100% of the daily cap, plus the provider's own budget alerts | 80% → notify; 100% → page |
| Database | Render metrics | CPU > 80% for 15 min; storage > 75%; connections > 80% of max |
| Jobs | Backup, purge and drill output | Missing or failed backup → page the next morning; failed drill → SEV2 |
| Payments | Paystack dashboard + `webhook_events` | Any 401 on the webhook (signature) → investigate |

Every request has an `x-request-id`. Users quote it from error messages and support finds it in the logs.

## 8. Performance and scaling

**Measured on one worker (QA run):**
- 96 requests/second with 0 errors;
- p95 latency 0.9 s at 50 concurrent users, 1.6 s at 100 (queueing).

Production starts with 2 instances × 2 workers. Every page settled under 3 s locally.

**Before launch:** rerun `python -m tests.qa.load 100 30` against staging, then raise instances until p95 < 800 ms.

**What scales:**
- **API and web:** stateless; per-IP limits now live in Postgres. Autoscaling needs a Pro workspace (`scaling.minInstances`/`maxInstances`/`targetCPUPercent`).
- **Database:** resize vertically; read replicas exist on Render if reads ever dominate.
- **Remaining per-process limiter:** the integrations token bucket, which only smooths calls. Provider fetch caps are enforced through the shared cache.

**Known limits:**
- Free-plan AI requests queue per organisation (the race-condition fix).
- AI latency depends on the provider; the timeout is 60 s.

## 9. Security review and access controls

**Already in place and tested:**
- Row-level security on every tenant table; the app connects as a non-owner role. Cross-tenant sweep: 630 requests, 0 leaks.
- Argon2 password hashes.
- Short access tokens; refresh-token reuse detection; per-account lockout plus per-IP limits.
- Password reset with no account enumeration.
- CSRF header on all browser writes.
- Nonce CSP, X-Frame-Options, nosniff and Referrer-Policy; `no-store` caching on API responses.
- Uploads: type sniffed from bytes, virus-scanned, never served inline; download tokens can't be forged.
- Integration tokens encrypted with key rotation.
- External actions require approval plus provider proof.
- Audit log of important actions, with real client IPs.

**Before launch:**
1. Run `scripts/create_roles.sql` on the managed database and confirm `eco_app` has no BYPASSRLS. **Must pass.**
2. Confirm the audit log shows real visitor IPs on staging (`TRUST_FORWARDED_FOR`, `TRUSTED_PROXIES`).
3. Turn on Dependabot or Renovate for pip, npm, Docker base images and GitHub Actions.
4. Two named production admins; GitHub, Render and Paystack access reviewed monthly; 2FA enforced.
5. An external penetration test before paid launch (phase 3), not before the closed beta.

## 10. Payments and subscriptions

**Status:** paid plans work in the app; the free limits, the unlimited paid plans, cancellation, grace period and downgrade are all tested. **Buying a plan doesn't exist yet.** The signed webhook receiver exists, and Paystack's docs confirm the signature scheme: HMAC-SHA512 of the payload with the secret key ([Paystack](https://paystack.com/docs/payments/webhooks/)). Until checkout is built, plans are activated manually with `python -m scripts.activate_plan --org … --plan pro --days 30 --ref <invoice> --by <name>` (tested; recorded in the audit log) for beta users who pay by invoice.

**To build before phase 3 (estimate 1–2 weeks):**
- Paystack checkout or plan subscription;
- handling `charge.success`, `subscription.create`, `subscription.disable`, `subscription.not_renew` and `invoice.payment_failed`;
- "cancel plan" in settings (account deletion requires it).

**Test plan (staging, test mode):**
1. Successful card payment.
2. Declined card.
3. Bank/USSD flows offered in Nigeria.
4. Renewal.
5. Failed renewal: grace period, then back to Free with nothing deleted.
6. Cancel: access until period end.
7. Duplicate webhook is idempotent.
8. Unsigned or forged webhook is refused.
9. Webhook arriving before the redirect.
10. Refund.

Then one real live-mode payment by the founder, refunded.

Paystack retries webhooks every 3 minutes for the first 4 attempts in live mode, then hourly for 72 hours, so reconcile anything older daily.

## 11. AI usage limits and cost controls

The controls work in layers:

1. **Per user:** 20 requests a minute.
2. **Free plan:** 30 generations a month per organisation, now race-proof.
3. **Paid plans:** a monthly fair-use ceiling per user (`FAIR_USE_MONTHLY_USD_PER_USER`, default $50).
4. **Platform-wide:** a daily cap (`AI_DAILY_BUDGET_USD`) pauses new generations with a clear message until midnight UTC.
5. **Provider-side:** a spend limit and budget alerts on the provider project.

**Correct prices are mandatory:** set `AI_MODEL_PRICES` from the provider's price page. With $0 prices, every cap above silently does nothing; the app now refuses to start that way when deployed.

**Setting the daily cap:**
- Expected daily active users × average cost per user per day × 3.
- Start at about $20/day in phase 1 and review weekly.
- Alerts go out at 80%.

**Provider tiers:** OpenAI reportedly consolidated its usage tiers on 6 Oct 2026, with organisation monthly limits of $500 (Build), $5,000 (Launch) and $200,000 (Grow) ([Layer3 Labs, 6 Nov 2026](https://www.layer3labs.io/guides/openai-api-usage-tiers)). That's a secondary source; check your organisation's limits page before launch. A low tier can cap you before your own budget does.

**Weekly review:**
- cost per active user and per division;
- failed or invalid outputs;
- top users against fair use.

## 12. Privacy policy, terms and data handling

**Built:**
- Download my data.
- Delete my account (immediate anonymisation; purge after 30 days).
- Terms acceptance stored with version and time.
- Draft `/privacy` and `/terms` written from what the app actually collects, who receives it and how long it's kept, plus draft retention periods.

**Legal duties (Nigeria Data Protection Act 2023, from Nigerian firms' summaries; confirm with counsel):**

| Duty | Applies how | Owner |
|---|---|---|
| Breach notice | NDPC within 72 h of becoming aware of a risky breach; users immediately if high risk ([Afriwise](https://www.afriwise.com/blog/data-breaches-compliance-obligations-under-the-nigerian-data-protection-act-2023)) | Incident lead |
| Registration as a controller of major importance | Covers e.g. processing data of more than 200 people in 6 months, or providing commercial ICT services; register within 6 months ([TNP](https://tnp.com.ng/understanding-the-compliance-obligations-of-data-controllers-and-processors-under-the-nigeria-data-protection-act/)) | Founder + counsel |
| Data Protection Officer | Required for major-importance controllers; contact details public and filed with NDPC (s.32) | Founder |
| Impact assessment | Before high-risk processing, e.g. AI profiling and career assessments (s.28) | DPO |
| Annual audit return | By 31 March, via a licensed compliance organisation | DPO |
| Processing agreements | Render, AI provider, Paystack, email provider, Sentry, S3 provider; an addendum for agencies uploading client data | Counsel |
| Cross-border transfer | Hosting in Frankfurt needs a documented basis | Counsel |

Fines for major-importance controllers: the greater of ₦10 million or 2% of the previous year's gross revenue. If you serve EU or UK users, GDPR applies too; the same features cover access, erasure and portability.

## 13. Support and incident response

**Support:**
- One inbox (`support@<domain>`) with a help desk (Help Scout, Freshdesk or similar) and an in-app "Contact support" link.
- Reply within 1 working day during beta, 4 hours for paid customers.
- Saved replies for: reset email not received, AI paused, plan or payment, deleting the account, upload rejected.
- Support staff ask for the request ID shown in error messages.
- Status page on its own domain (e.g. `status.<domain>`).

**Incident response** (`runbooks/incident-response.md`):
- SEV1–3 definitions.
- First-15-minutes checklist: roll back first if there was a recent deploy.
- Mitigation switches: `OUTBOUND_HTTP_ENABLED`, `AI_DAILY_BUDGET_USD`, maintenance mode.
- The NDPA breach steps.
- Blameless review within 5 working days.
- Weekly on-call rota between the two production admins.

## 14. Beta testing and feedback

**Phase 1, closed beta:**
- 20–40 invited users, spread across the four personas: business owners (Lagos/Awka), social media managers or agencies, freelancers, remote job seekers.
- Free plan raised for them, or manual paid plans.
- Each tester gets a short brief with three tasks for their division.

**Feedback channels:**
- an in-app "Send feedback" button (to the help desk, with the page and request ID);
- a 5-question survey after 7 days (task success, AI usefulness 1–5, trust in outputs, would pay, price expectation in naira);
- two 20-minute calls a week;
- a WhatsApp group for quick reports.

**Measure:**
- activation: first saved draft or profile within 24 h;
- week-1 return rate;
- AI failure rate;
- cost per active user;
- support tickets per user;
- crash-free sessions.

**Exit criteria for phase 2:**
- no SEV1 for 14 days;
- p95 < 800 ms;
- AI failure < 3%;
- ≥ 60% of testers complete a core task;
- no data-isolation bug.

## 15. Rollback and recovery

**Application rollback:**
- Automatic in the production pipeline when the smoke test fails; manual by redeploying the previous SHA (`runbooks/deploy-and-rollback.md`).
- Restore the matching environment variables with the image. Rehearsal showed older releases don't understand newer config values.
- Schema stays: additive-only migrations are enforced by the gate, and the previous release was rehearsed on the new schema.

**Data recovery:** `runbooks/disaster-recovery.md`. PITR to a new instance, or restore the logical backup with the drilled commands, then smoke-test.

**Deleted by mistake:**
- A user who deletes their account by mistake has a 30-day grace period for their workspaces. Support can restore them by clearing `deleted_at`; the identity can't be restored.
- Files are protected by bucket versioning.

## Go-live checklist

**Owner actions (accounts, legal, money)**
- [ ] Domain bought; registrar lock + 2FA; DNS provider chosen
- [ ] Render workspace (Pro, for 7-day PITR and HA); staging and production blueprints applied
- [ ] S3-compatible buckets: staging files, production files (versioned), backups in a separate account (versioned, object lock)
- [ ] AI provider: separate staging and production projects, keys, spend limits and alerts, tier confirmed; `AI_MODEL_PRICES` set from the price page
- [ ] Email provider: domain verified with SPF, DKIM and DMARC; SMTP credentials
- [ ] Sentry project; uptime checker; log destination; status page
- [ ] Paystack: business verified, test keys in staging, live keys in production, webhook URL set
- [ ] Counsel: privacy policy and terms finalised (remove DRAFT marker and placeholders), DPA templates, NDPC registration decision, DPO named
- [ ] Support inbox and help desk; on-call rota; contacts filled in the incident runbook

**Technical, on staging**
- [ ] `create_roles.sql` works on Render Postgres; `eco_app` has no BYPASSRLS
- [ ] Pipeline deploys staging from `main`; deploy-hook image format confirmed
- [ ] `/ready` green with real ClamAV and the real bucket
- [ ] Smoke test 100% green, including real AI generation and a real upload
- [ ] A real password-reset email arrives
- [ ] Audit log shows real visitor IPs
- [ ] Load test: p95 < 800 ms at expected peak
- [ ] Backup ran overnight; restore drill passed at realistic volume; time recorded
- [ ] Rollback rehearsed through the pipeline (deploy N, then N-1)
- [ ] Alerts fire: stop the API, exceed the AI budget, fail a backup
- [ ] Dependabot or Renovate on; images pinned by digest

**Production, launch day**
- [ ] Legal gate passes; `LEGAL_TERMS_VERSION` set
- [ ] Production deploy approved by a second person; smoke test green
- [ ] Synthetic monitoring account works; uptime checks green
- [ ] Staging still `noindex`; production indexed only on public pages
- [ ] First real payment (if phase 3) made and refunded

## Outstanding risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Legal drafts not approved in time; NDPA registration or DPO missed | Medium | High (fines, can't launch) | Start counsel now; the pipeline blocks deploy while drafts remain |
| Render Postgres can't create the restricted `eco_app` role | Unknown | High (RLS wouldn't apply) | Verify day 1; fall back to AWS RDS or Neon |
| No checkout means no revenue | Certain until built | Medium | Phases 1–2 free or invoiced; build checkout before phase 3 |
| Real AI quality or latency differs from scripted tests | Medium | High | Live evals and staging smoke with the real model; beta exit criterion on AI failure rate |
| AI cost spike or abuse | Medium | Medium | Five layers of limits; correct prices enforced; alerts at 80% |
| Frankfurt latency for Nigerian users | Medium | Medium | Measure from Lagos in beta; Lagos Local Zone later |
| Email deliverability (resets in spam) | Medium | Medium | SPF/DKIM/DMARC; dedicated sending domain; monitor bounces |
| Single region, single host | Low | High | PITR + off-account backups + drilled restore; RTO 4 h |
| ClamAV memory or signature updates on the host | Medium | Medium (uploads stay "pending") | `/ready` checks the scanner; alert; size per staging |
| Deploy-hook or cron-image details differ from docs | Low | Low | Verified on staging before prod; manual dashboard deploy as fallback |
| Two-person team: on-call fatigue, single points of knowledge | High | Medium | Runbooks; rota; alerts tuned to pages only for SEV1/2 |

## Phased rollout

**Phase 0: setup (week 1–2)**
- Accounts and keys created; staging live via the pipeline; every "on staging" checklist item green.
- Counsel engaged.
- Gate: staging smoke 100%; restore drill and load test pass.

**Phase 1: closed beta (weeks 3–6)**
- 20–40 invited testers across the four personas.
- Production environment live with approved legal pages; free or manually activated plans; sign-up by invite list.
- Gate: the phase-1 exit criteria in section 14.

**Phase 2: open beta (weeks 7–10)**
- Public sign-up, Free plan only.
- Paid plans by invoice and manual activation for early adopters.
- Paystack checkout built and tested on staging.
- External penetration test.
- Gate: checkout test plan passes; no open High findings; support response targets met.

**Phase 3: paid launch (week 11+)**
- Checkout live; marketing starts.
- Daily AI budget raised in steps.
- Weekly cost and reliability review.

**Phase 4: scale (when needed)**
- Autoscaling.
- Read replica if reads dominate.
- Integrations planned earlier (Instagram insights, GA4, …) as their app reviews clear.
- Lagos Local Zone if latency data says so.

## Sources

- Render: [Blueprint spec](https://render.com/docs/blueprint-spec), [Postgres extensions](https://render.com/docs/postgresql-extensions), [PITR, replicas and extensions](https://render.com/articles/postgres-features-that-matter-for-production-pitr-read-replicas-and-native-exten)
- AWS: [Available Local Zones](https://docs.aws.amazon.com/local-zones/latest/ug/available-local-zones.html)
- Paystack: [Webhooks](https://paystack.com/docs/payments/webhooks/)
- NDPA: [Afriwise on breach obligations](https://www.afriwise.com/blog/data-breaches-compliance-obligations-under-the-nigerian-data-protection-act-2023), [TNP on controller obligations](https://tnp.com.ng/understanding-the-compliance-obligations-of-data-controllers-and-processors-under-the-nigeria-data-protection-act/)
- OpenAI tiers (secondary): [Layer3 Labs](https://www.layer3labs.io/guides/openai-api-usage-tiers)
