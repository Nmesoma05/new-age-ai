# External integrations

Provider facts were checked against official documentation on **12 Nov 2026**. APIs, prices and review rules change
often, so re-check a provider's page before enabling or building it. The live catalog is
`GET /v1/integrations/catalog` (from `app/integrations/catalog.py`, the single source of truth for this page).

**Status key:**
- **Implemented**: code, tests and UI exist. Tests run against fake providers, because this build environment
  has no internet access. None of the three has been exercised against the live provider yet; see
  "Before go-live" below.
- **Planned**: researched and specified only. No code calls these providers.

---

## 1. Implemented integrations

| # | Integration | Divisions | Access | Auth |
|---|---|---|---|---|
| 1 | Exchange rates (ExchangeRate-API, open access) | Freelancer (Business-ready) | Read-only | None (public) |
| 2 | Remotive remote-jobs feed | Freelancer | Read-only | None (public) |
| 3 | YouTube channel analytics (Data API v3 + Analytics API) | Creator | Read-only | OAuth 2.0 + PKCE |

### 1.1 Exchange rates: ExchangeRate-API open endpoint

- **Docs:** https://www.exchangerate-api.com/docs/free
- **Capabilities verified:**
  - Covers about 160 currencies, including NGN, KES, GHS, ZAR, EGP, XOF, XAF, ETB, UGX, TZS and RWF.
  - Rates update once a day.
  - The provider asks for at most one request per hour. HTTP 429 means you've been rate limited, and it lifts after about 20 minutes.
  - Attribution is required ("Rates By Exchange Rate API", linked). Caching is allowed; redistribution is not.
  - No regional restrictions are stated.
  - We chose this over ECB-based APIs (e.g. Frankfurter) because ECB reference rates don't cover most African currencies. [Medium confidence: Frankfurter's currency list page didn't load when checked.]
- **Data:** read `rates[base→X]`, `time_last_update_utc`. Writes nothing.
- **Auth:** none. No key is stored.
- **Caching and limits:**
  - One app-wide row per base currency in `external_cache`, kept for 12 hours. At most one fetch per base per 12 hours, whatever the number of users.
  - Client limit: 0.5 requests/second, 2 attempts.
- **Errors and fallback:**
  - If the provider fails and a cached copy exists, we serve it marked `stale: true`, with its date.
  - If no cached copy exists, the API returns an error and the UI says "Not converted: the exchange-rate service isn't available right now". No number is ever invented.
- **Display:** "≈ NGN 3,001,000–4,501,500 at the daily rate (date)", plus "Indicative daily reference rate, not what a bank or payment provider will pay out" and the attribution link.
- **Approval:** none (read-only public data).
- **Endpoint:** `GET /v1/fx/convert?amount=&from=&to=` (any signed-in user).
- **Switch off:** `FX_PROVIDER_ENABLED=false`.

### 1.2 Remotive public jobs feed

- **Docs:** https://github.com/remotive-com/remote-jobs-api
- **Capabilities and terms verified:**
  - Endpoint: `GET https://remotive.com/api/remote-jobs`.
  - Fields: id, url, title, company_name, category, job_type, publication_date, candidate_required_location, salary, description (HTML).
  - Fetch about 4 times a day at most; more than 2 requests a minute get blocked.
  - Listings are delayed 24 hours.
  - You must link back to Remotive and credit it.
  - Don't submit the jobs to other job sites.
  - Don't use the jobs to collect sign-ups or emails.
- **Data:** reads listings. Writes nothing to Remotive.
  - An import creates an `opportunities` row with `source=integration`, `source_name=Remotive`, the Remotive URL and `status=unverified`.
  - Salary is kept as the listing's own text and never parsed into numbers.
  - Description HTML is stripped of scripts and tags.
- **How the terms are enforced in code:**
  - One shared snapshot for the whole app, refreshed at most every 6 hours (≤4 fetches/day). Searching runs locally against that snapshot.
  - Rate limiter: 1 request per 40 seconds.
  - Only `https://remotive.com/...` URLs are kept.
  - Every screen that shows the feed carries the "Jobs from Remotive" link and the 24-hour note.
  - Nothing is posted anywhere.
- **Location mapping:**
  - "Worldwide" maps to global.
  - Recognised country or region names map to tokens.
  - Anything else stays as text, and eligibility shows as "unclear". We never guess.
- **Errors and fallback:**
  - If a fetch fails and an old snapshot exists, we serve it marked stale.
  - If no snapshot exists, the UI says the feed isn't available. Adding listings by hand and the job-board directory keep working.
- **Approval:** none to search or save. The user must still open the source and confirm the job is open ("Not verified" until they do).
- **Endpoints:**
  - `GET /v1/workspaces/{id}/jobs/remotive?q=&category=` (ws.read).
  - `POST .../jobs/remotive/import {job_id}` (ws.write; 409 if already saved; 404 `job_gone` if it's left the feed).
- **Switch off:** `REMOTIVE_ENABLED=false`.

### 1.3 YouTube channel analytics

- **Docs:**
  - https://developers.google.com/youtube/analytics/v1/reports/query
  - https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification
- **Capabilities verified:**
  - Reports endpoint: `GET youtubeanalytics.googleapis.com/v2/reports` with `ids=channel==MINE`, `startDate`, `endDate`, `metrics`, and `dimensions=video`.
  - `channels.list?mine=true` returns the channel id, title and subscriber count.
  - `videos.list` returns titles and publish dates.
  - Data API default quota: 10,000 units/day per project; list reads cost about 1 unit.
- **Access requirements (before public launch):**
  - A Google Cloud project with both APIs enabled and an OAuth web client.
  - Both scopes are sensitive, so Google's verification is required: a privacy policy on your domain, domain verification, a demo video and brand verification. Google quotes 3–5 business days.
  - Until verified, only listed test users can connect, up to a user cap.
  - Regional availability: wherever YouTube and Google OAuth are available. Nothing extra was found for Nigeria or Africa.
- **Scopes:** `youtube.readonly` and `yt-analytics.readonly`. Read-only; both are required, and a connection that grants only one is refused (`scopes_missing`).
- **Data:**
  - Reads the channel id and title, subscribers (unless hidden), and per-video views, likes, comments and shares for a date range (default: the last 28 full days).
  - Writes into our own tables only:
    - `follower_snapshots`: one row per day.
    - `post_metrics`: one row per video per capture day, updated rather than duplicated on re-sync.
  - Both are written with `source=integration`. Manual rows are never overwritten.
  - Nothing is written to YouTube.
- **Auth flow:** see §3 below.
- **Errors:**
  - 401 → refresh. `invalid_grant` → `needs_reauth`, and the UI shows "Reconnect".
  - 403 → `permission_denied`.
  - If the channel id behind the token changes, the sync is refused with `account_changed` (reconnect).
  - 429/5xx → retried with backoff (GET only).
- **Approval:** connecting needs an org owner or admin. Syncing (read-only) needs workspace write. Nothing is ever posted.
- **Lag:** YouTube Analytics usually lags 2–3 days. This is shown after each sync. [Medium confidence on the exact lag; it varies.]
- **Endpoints:**
  - `POST /v1/workspaces/{id}/integrations/youtube/connect {return_to}` → `{authorization_url}`.
  - `POST /v1/integrations/oauth/complete {state, code | error}`.
  - `POST .../integrations/{id}/sync {start?, end?}`.
  - `DELETE .../integrations/{id}`.
  - `GET .../integrations`: metadata only, never tokens.
- **Config:** `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` and `PUBLIC_WEB_URL`. Register `PUBLIC_WEB_URL/integrations/callback` as the redirect URI.
- **Fallback:** manual entry and CSV upload, unchanged. Without the config, the UI shows "Not set up on this server" and no Connect button.

---

## 2. Planned integrations (not built)

None of these is called by the code. Each needs the access steps listed before it can be built, and all of them follow the framework in §3.

### Priority 2: read-only

| Integration | Divisions | Key requirements (verified 12 Nov 2026) | Fallback until built |
|---|---|---|---|
| Instagram insights (Meta) | Creator, Business | <ul><li>Professional accounts only.</li><li>Advanced Access via App Review + Business Verification.</li><li>Long-lived tokens last 60 days.</li><li>Rate limit: 4,800 × impressions per 24h.</li></ul> | Manual/CSV |
| Facebook Page insights | Creator, Business | <ul><li>`pages_read_engagement` + `read_insights`.</li><li>The person connecting needs the "analyze" task on the Page.</li><li>Several metrics were deprecated by 15 Jun 2026.</li></ul> | Manual/CSV |
| LinkedIn Page analytics | Creator, Business | <ul><li>Community Management API: legal entity, Development tier, then Standard tier with a screencast.</li><li>A rejected app can't reapply.</li><li>A Page super admin must verify the app.</li></ul> | Manual/CSV |
| TikTok profile & video stats | Creator | `user.info.basic/stats`, `video.list`; scope review | Manual/CSV |
| X metrics | Creator | Pay-per-use: even reads cost money ($0.001–$0.010 per resource), so a budget cap is needed first | Manual/CSV |
| Google Analytics 4 | Business | <ul><li>Core quota: 200k tokens/day, 40k/hour, 10 concurrent requests.</li><li>Sensitive-scope verification.</li></ul> | Manual/CSV results |
| Google Business Profile | Business | <ul><li>Access form; quota is 0 until approved.</li><li>Scope: `business.manage`.</li></ul> | Manual/CSV results |
| HubSpot CRM (read) | Business | <ul><li>OAuth; access tokens last 30 minutes.</li><li>Token endpoint `api.hubspot.com/oauth/2026-09/token`.</li></ul> | Manual/CSV results |
| Brave Search (live research) | All | Metered at about $5 per 1,000 requests (free tier removed Feb 2026), so a budget cap is needed | Research uses the user's own documents |
| Upwork | Freelancer | **Unverified**: docs page didn't load; requires an approved API key | Paste listings |

### Priority 3: writes (publish or send)

Every one of these requires approval per action (§4).

| Integration | Key requirements | Fallback |
|---|---|---|
| Instagram publishing | `instagram_business_content_publishing`, App Review | Copy, post manually, "Mark published" |
| Threads publishing | `threads_content_publish`; 250 posts per 24h | Manual |
| LinkedIn posting | Community Management Standard tier | Manual |
| TikTok posting | `video.publish`/`video.upload`; private-only until audited | Draft upload / manual |
| YouTube upload | 100 `videos.insert`/day default; audit for production | Manual |
| Google Calendar | `calendar.events.owned` | .ics download |
| Email campaigns | Provider not chosen; SPF/DKIM/DMARC, opted-in lists | Copy into the user's own tool |

### Priority 4: spending money

Each needs both workspace admin and org owner/admin approval, with the cost shown.

| Integration | Key requirements | Fallback |
|---|---|---|
| X posting | $0.015 per post, $0.20 per post containing a URL | Manual |
| WhatsApp Cloud API | <ul><li>Per-message pricing since 1 Jul 2025.</li><li>Templates and opt-in required.</li><li>Service messages free inside the 24h window.</li><li>Nigeria rates weren't visible on the pricing page [Low confidence: check the rate card].</li></ul> | Export for the WhatsApp Business app |
| SMS, Nigeria (Termii/Twilio) | <ul><li>Pre-registered alphanumeric sender ID (about 3 weeks).</li><li>Numeric senders fail on MTN/Airtel/9mobile.</li><li>No two-way SMS (Twilio); DND registry applies.</li></ul> | CSV export |
| Meta ads | <ul><li>Dev tier by default.</li><li>Standard Access needs App Review, a live app, 1,500 calls in 30 days and <10% errors.</li><li>Campaigns are created PAUSED.</li></ul> | Ads Manager + record results |
| Google Ads | <ul><li>Since 9 Sep 2026, access is per Cloud project: Explorer (2,880 production operations/day) → Basic (15,000) → Standard (audit).</li><li>Campaigns are created paused.</li></ul> | Google Ads UI + record results |
| Paystack billing | <ul><li>**Partly present:** the inbound webhook receiver (signature check, raw event stored) exists from the backend phase.</li><li>Checkout and plan calls aren't built.</li><li>Paystack doesn't retry failed subscription charges.</li><li>The signature scheme still needs confirming against current docs.</li></ul> | Admin activates plans |

The full detail for each (docs URL, scopes, limits, approval rule) is in `GET /v1/integrations/catalog` and is shown in
Settings → Integrations → "What it needs".

---

## 3. The framework every integration uses

### Authentication: OAuth 2.0 authorization code + PKCE (`app/integrations/oauth.py`)

1. An org owner or admin clicks **Connect**.
   - The server creates a random `state` (32 bytes) and a PKCE verifier (S256).
   - It stores only `sha256(state)` and the encrypted verifier in `oauth_states`, for 10 minutes. That table is system-only under row-level security.
   - The browser receives only the provider's authorize URL.
2. The provider redirects back to the web app's `/integrations/callback` page.
   - The page posts `{state, code}` through the same-origin proxy, with the user's session.
   - It then strips `code` and `state` from the address bar and history.
3. The server checks the state:
   - It must exist, belong to the **same user**, be **unused** and be **unexpired**.
   - It's marked used in its own committed transaction before anything else, so it stays single-use even if the exchange fails.
4. The server exchanges the code together with the verifier.
   - A stolen code is useless without the verifier.
   - The exchange is not retried automatically.
5. Then:
   - Every requested scope must have been granted.
   - The org admin role is re-checked, in case it changed while the user was at the provider.
   - The account identity is fetched.
   - If any of this fails, the token is revoked at the provider and not stored.
6. One row per (workspace, provider, external account) is upserted, and `integration.connected` is written to the audit log (scopes and account name only).

### Tokens: storage, encryption, renewal, revocation

| Concern | How |
|---|---|
| Storage | `integrations.encrypted_credentials` (Fernet: AES-128-CBC + HMAC-SHA256). Never returned by any API, never logged, decrypted in memory only for a call. Production recommendation: wrap the key with a cloud KMS. |
| Key rotation | `CREDENTIALS_ENCRYPTION_KEY` takes comma-separated keys: the first encrypts, all decrypt (MultiFernet). Rows are re-encrypted under the newest key on next use (`key_version`); `crypto.rotate_blob` can do a bulk pass. Remove an old key only after that. |
| Renewal | <ul><li>Refreshed when within 2 minutes of expiry, under a row lock, in its own transaction, so a rotated refresh token is saved even if the request then fails.</li><li>`invalid_grant`/401 → status `needs_reauth`, with a UI prompt to reconnect.</li><li>Other failures keep the old token and count a failure.</li></ul> |
| Revocation | <ul><li>Calls the provider's revoke endpoint (best effort), then always destroys our copy (`\x00`) and keeps the row as `revoked` for the audit trail.</li><li>If the provider didn't confirm, the response says so and links to https://myaccount.google.com/permissions.</li></ul> |
| Who | <ul><li>Connect/disconnect: org owner or admin.</li><li>Sync: workspace write.</li><li>Viewing connection health: workspace read.</li><li>Pasted credentials for catalog providers are refused on the older `/v1/orgs/{id}/integrations` endpoint (`use_connect_flow`).</li></ul> |
| Isolation | <ul><li>Row-level security: integrations are readable only by org admins and the system context.</li><li>Workspace endpoints filter by workspace id.</li><li>Tests check that another tenant gets 404 and sees 0 rows.</li></ul> |

### Calls: errors, retries, rate limits, audit (`app/integrations/http.py`)

- **Host allowlist** per provider, HTTPS only, redirects not followed. This prevents server-side request forgery (SSRF), where a user could make the server fetch internal URLs.
- **Timeouts and size:** 5s connect, 20s total by default (30s for Remotive); responses capped at 5 MB.
- **Retries:**
  - Only for idempotent requests, on network errors, 429 and 5xx.
  - Exponential backoff with jitter; `Retry-After` honoured up to 30s; 3 attempts by default.
- **Writes are never retried blindly:**
  - A timeout after sending raises `OutcomeUnknown`, and the action is recorded as failed/outcome-unknown so the user can check before trying again.
  - A connect failure before sending says "nothing was sent".
- **Rate limiting:** a token-bucket limiter per provider.
- **Circuit breaker:** opens after 5 failures and cools down for 60s. Rate limiting (429) doesn't count as a failure.
- **Errors map to stable codes:**
  - `needs_reauth` 409, `rate_limited` 429, `permission_denied` 403.
  - `provider_error`/`network_error`/`outcome_unknown` 502, `provider_unavailable`/`not_configured` 503.
  - Every error carries `retryable`.
- **Call log:** every attempt is written to `integration_calls` in its own transaction, so failures survive a rollback.
  - Logged: provider, operation, method, host, path **without query string**, status, outcome, attempt, latency.
  - Never logged: tokens or bodies.
  - Org admins can read it.
- **Audit events:** `integration.connected`, `integration.revoked` (with `provider_confirmed`), `integration.synced`, `opportunity.imported`.
- **Kill switch:** `OUTBOUND_HTTP_ENABLED=false` stops all provider traffic. The test suite sets this.
- **Known limit:** the rate limiter and breaker are in-process. Run one API instance, or move them to Redis before scaling out.

---

## 4. Approval before external actions

- Every publish, send or spend goes through `pending_actions`, the same flow used since the AI engine phase:
  - The AI proposes; it never executes.
  - A workspace admin approves.
  - `spend_money` also needs an org owner or admin.
  - Proposals expire.
  - Proposals that came from untrusted content are flagged.
- The contract for an executor (`app/ai/actions.py`), enforced in `approve_action`:
  - **A connected account is required.** The workspace must have a `connected` integration for the executor's provider. A `needs_reauth` or `revoked` connection, or one in another workspace, doesn't count (409 `no_connection`). The action stays pending.
  - **Idempotency key = action id.** It's passed to the executor, which must send it where the provider supports one.
  - **Proof or it didn't happen.** The executor must return `provider_ref` (the provider's id for what it created, sent or charged). Without it, the action is recorded as `failed / no_confirmation`. A URL alone isn't proof.
  - **Unclear outcomes:** `OutcomeUnknown` → `failed / outcome_unknown`, never retried automatically. A provider error → `failed / <code>`.
- **No write executor is registered in production.** A test asserts `EXECUTORS == {}` after app start. Approving any publish, send or spend still returns 409 `no_executor`: "copy the content and do it yourself".

---

## 5. Test plan

Automated tests run in `tests/integrations/` (31 tests), with providers faked via `httpx.MockTransport`:

| Area | Covered |
|---|---|
| HTTP client | <ul><li>GET retry then success.</li><li>`Retry-After` honoured and capped.</li><li>POST never retried.</li><li>Timeout → `OutcomeUnknown`; connect error → "nothing sent".</li><li>Host allowlist (other host, http://, look-alike suffix).</li><li>401/403 mapping; size cap.</li><li>Breaker opens.</li><li>Kill switch.</li><li>Call log has no query string or secrets.</li></ul> |
| OAuth | <ul><li>Authorize URL (S256, offline, exact scopes, redirect URI).</li><li>Tokens encrypted at rest and absent from every response.</li><li>Single-use state; wrong user; expired state; user cancelled.</li><li>Wrong PKCE verifier rejected.</li><li>Missing scope rejected.</li><li>Non-admin 403; planned provider 409; open-redirect `return_to` 422; not configured 503.</li><li>Reconnect upserts one row.</li></ul> |
| Tokens | <ul><li>Refresh on expiry.</li><li>Provider down → old token kept and failure counted.</li><li>`invalid_grant` → `needs_reauth`, and no further provider calls.</li><li>Reconnect restores.</li><li>Key rotation re-encrypts under the new key.</li><li>Revoke: confirmed vs. unconfirmed, with local secret destroyed either way.</li></ul> |
| YouTube sync | <ul><li>Metrics and subscriber snapshot written once per day (re-sync updates).</li><li>Account change detected.</li><li>Bad range 422.</li><li>403 surfaced.</li></ul> |
| Tenancy | Another tenant: 404 on list/sync/delete; 0 rows via RLS for integrations and oauth_states |
| FX | <ul><li>Conversion and attribution.</li><li>One fetch per base (cache).</li><li>Unsupported or bad currency.</li><li>Outage: stale-and-dated vs. honest failure.</li></ul> |
| Remotive | <ul><li>Search; HTML stripped; non-Remotive URLs dropped.</li><li>One fetch for many searches.</li><li>Import as unverified with credit; eligibility from location; duplicate 409; gone 404; contract kind.</li><li>Outage.</li><li>Only in freelancer workspaces.</li><li>Location mapping never guesses.</li></ul> |
| Approvals | <ul><li>No production executors.</li><li>OutcomeUnknown / provider error / no `provider_ref` / `None` all → failed and never retried.</li><li>`needs_reauth` or `revoked` connection blocks.</li><li>Another workspace's connection doesn't count.</li></ul> |

Browser tests (`eco-web/e2e/integrations.mjs`, 9 steps) run against the real web app, API and database, with fake providers and Google's consent page stood in for:
- Settings lists implemented vs. planned.
- Connect → callback → connected, with no token in the browser.
- Sync.
- Report rows labelled YouTube.
- Disconnect confirmed.
- Deny connects nothing.
- Remotive find, save, credit and unverified status.
- Attributed FX on pay.
- Phone width.

### Before go-live (manual, needs internet and real accounts)

1. **FX:** call `/v1/fx/convert` for USD→NGN and confirm the rate and update time match the provider's page.
2. **Remotive:**
   - Fetch once, confirm the field names are unchanged and that 2 searches cause 1 upstream call (check `integration_calls`).
   - Confirm the terms on the GitHub page are unchanged.
3. **YouTube:**
   - Create the Google Cloud project, enable both APIs, set the consent screen and add test users.
   - Connect a real channel. Compare one video's views with YouTube Studio for the same dates.
   - Revoke at myaccount.google.com, then sync and expect "Reconnect".
   - Rotate the encryption key and sync again.
4. Submit the sensitive-scope verification before inviting non-test users.
5. Confirm that `OUTBOUND_HTTP_ENABLED`, `REMOTIVE_ENABLED` and `FX_PROVIDER_ENABLED` are set as intended in each environment.

---

## 6. Sources (checked 12 Nov 2026)

- ExchangeRate-API open access: https://www.exchangerate-api.com/docs/free
- Frankfurter: https://frankfurter.dev
- Remotive API: https://github.com/remotive-com/remote-jobs-api
- YouTube Analytics reports: https://developers.google.com/youtube/analytics/v1/reports/query
- YouTube Data API quota: https://developers.google.com/youtube/v3/getting-started
- Google sensitive-scope verification: https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification
- Instagram Platform App Review: https://developers.facebook.com/docs/instagram-platform/app-review
- Facebook Page insights: https://developers.facebook.com/documentation/pages-api/platforminsights/page
- X API pricing: https://docs.x.com/x-api/getting-started/pricing
- LinkedIn Community Management review: https://learn.microsoft.com/en-us/linkedin/marketing/community-management-app-review
- TikTok scopes: https://developers.tiktok.com/doc/tiktok-api-scopes/
- Threads API: https://developers.facebook.com/documentation/threads/overview
- Google Ads access levels: https://developers.google.com/google-ads/api/docs/api-policy/access-levels
- Meta Marketing API access: https://developers.facebook.com/docs/marketing-api/access/
- WhatsApp pricing: https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing
- GA4 Data API quotas: https://developers.google.com/analytics/devguides/reporting/data/v1/quotas
- Google Business Profile Performance API: https://developers.google.com/my-business/reference/performance/rest
- HubSpot OAuth tokens: https://developers.hubspot.com/docs/api-reference/latest/authentication/manage-oauth-tokens
- Twilio Nigeria SMS guidelines: https://www.twilio.com/en-us/guidelines/ng/sms
- Brave Search API plans: https://api-dashboard.search.brave.com/app/plans
- Paystack subscriptions: https://paystack.com/docs/payments/subscriptions/
