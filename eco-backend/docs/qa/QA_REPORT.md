# QA report: three-division AI ecosystem

**Date:** 13 Nov 2026
**Builds tested:** eco-backend (FastAPI + PostgreSQL 16 with row-level security) and eco-web (Next.js 15, production build)
**Browser:** Chromium (Playwright)

**Verdict:** 14 bugs found: 4 High, 7 Medium, 3 Low, none Critical. All 14 are fixed, each has a regression test, and the full regression run passed after the last fix.

Nothing below is marked passed unless it ran. Items that could not run in this environment are listed as **Blocked**. Items not attempted are listed as **Untested**.

## 1. Totals (final run, after all fixes)

| Suite | Executed | Passed | Failed | Blocked/skipped |
|---|---|---|---|---|
| Backend tests (pytest, real Postgres with RLS) | 296 | 296 | 0 | 1 (live AI evals) |
| …of which new QA tests (`tests/qa/`, 34 functions) | 35 | 35 | 0 | 0 |
| Browser: Creator workflows (`run.mjs`) | 16 | 16 | 0 | 0 |
| Browser: Business workflows | 13 | 13 | 0 | 0 |
| Browser: Freelancer workflows | 14 | 14 | 0 | 0 |
| Browser: Integrations | 9 | 9 | 0 | 0 |
| Browser: QA personas + accessibility/mobile/performance/security sweep (`personas.mjs`) | 21 | 21 | 0 | 0 |
| Cross-tenant sweep (every route × victim ids) | 630 requests | 630 | 0 | 0 |
| Load test (50, then 100 concurrent users) | 4,000 requests | 4,000 (0 errors) | 0 | 0 |
| Lint (ruff), typecheck (tsc), production build | 3 | 3 | 0 | 0 |

The API log for the whole browser regression contains **0 server errors** (no tracebacks).

## 2. Results by area

| # | Area | Result | Evidence (executed) | Not covered |
|---|---|---|---|---|
| 1 | Registration, login, recovery | **Pass** after fixes (BUG-03, 05, 08, 11) | <ul><li>Sign-up validation and limits.</li><li>Case-insensitive unique email.</li><li>Wrong password shows an error.</li><li>Per-account lockout plus per-IP limit.</li><li>Refresh-token reuse revokes the family.</li><li>Forgot → email link → reset → old sessions signed out.</li><li>Change password keeps this device.</li><li>No account enumeration.</li><li>Open redirect blocked.</li><li>Keyboard-only sign-in.</li></ul> | Real email delivery (Blocked) |
| 2 | Product selection and access | **Pass** | <ul><li>Wrong-product endpoints refused.</li><li>Role matrix: an editor can't connect accounts, approve or open another client.</li><li>Only 5 static routes answer without login, pinned by a test.</li></ul> | — |
| 3 | Onboarding (all 3 divisions) | **Pass** | <ul><li>Creator: solo and agency.</li><li>Business: solo.</li><li>Freelancer: six steps.</li><li>Required fields enforced on a phone (D1).</li></ul> | — |
| 4 | Navigation and responsive | **Pass** after BUG-06 | <ul><li>22 pages at 1360px and 360px: no sideways scroll.</li><li>The sweep confirms it reached each real page.</li><li>Page titles are correct (BUG-13).</li></ul> | Real phones and tablets (Untested) |
| 5 | Core features and workflows | **Pass** | 52 workflow steps across the four existing browser suites, plus 15 persona steps | — |
| 6 | AI agent selection, output, memory | **Pass with scripted model**; live model **Blocked** | <ul><li>Orchestrator routing.</li><li>29 agent tests (validators, refusals, no invented facts).</li><li>Retrieval never crosses workspaces or orgs.</li><li>Private memory reaches only its author.</li><li>Prompt-injection detection.</li><li>Free-limit race (BUG-14).</li></ul> | Output quality from the real model: needs an API key and internet (Blocked) |
| 7 | Uploads, saving, editing, exports | **Pass** after BUG-02, 04 | <ul><li>Type is sniffed from bytes; a disguised program is refused.</li><li>HTML is never served as HTML.</li><li>Download tokens can't be forged or swapped.</li><li>Unicode (Igbo) filenames and titles.</li><li>CSV and ICS formula/header injection neutralised.</li><li>HTML export escaped.</li><li>Version history.</li></ul> | Virus scanning with a real scanner (dev scanner only) |
| 8 | Workspace and client isolation | **Pass** | <ul><li>630-request cross-tenant sweep over all 177 route-methods: 0 leaks.</li><li>RLS tests at the database level.</li><li>Editor limited to one client in the UI (B2).</li></ul> | — |
| 9 | Subscription, billing, usage | **Pass** after BUG-14 | <ul><li>Free 30/month limit, including under parallel requests.</li><li>Paid is unlimited.</li><li>Cancelled keeps access until period end.</li><li>Past-due grace period.</li><li>Downgrade makes extra workspaces read-only.</li><li>Seat limit.</li><li>Fair use and per-minute limits.</li><li>Webhook signature and idempotency.</li></ul> | Real Paystack checkout (not built; signature scheme unconfirmed) |
| 10 | Integrations and approvals | **Pass against fakes**; live **Blocked** | <ul><li>OAuth/PKCE, tokens, refresh, revoke, retries, breaker.</li><li>Remotive and exchange rates.</li><li>Approvals need a connection and provider proof.</li><li>9 browser steps.</li></ul> | Real Google/YouTube, Remotive, ExchangeRate-API: no internet here (Blocked) |
| 11 | API validation, errors, rate limits | **Pass** after BUG-09, 11 | <ul><li>Malformed, oversized (3MB/25MB) and deeply nested bodies → clean 4xx.</li><li>No stack traces or SQL in errors.</li><li>Request IDs.</li><li>`no-store` caching.</li><li>Every limit returns 429 with Retry-After.</li></ul> | — |
| 12 | Accessibility, performance, mobile | **Pass** after BUG-06, 07, 13 | <ul><li>axe WCAG 2 A/AA: 0 serious/critical on 22 pages.</li><li>Touch targets ≥24px at 360px.</li><li>Every page settles under 3s.</li><li>Load test: 0 errors.</li></ul> | <ul><li>Screen readers (Untested, manual).</li><li>Firefox/Safari: only Chromium is installed (Blocked).</li></ul> |
| 13 | AuthN/AuthZ and common vulnerabilities | **Pass** after BUG-05, 10, 11, 12 | <ul><li>JWT: forged, `alg=none`, expired and wrong-type tokens rejected.</li><li>Mass assignment ignored.</li><li>SQL injection and XSS strings stored as data.</li><li>CSRF header required.</li><li>CORS allowlist.</li><li>Nonce CSP with 0 violations.</li><li>Clickjacking blocked.</li><li>Real client IP, which can't be spoofed by calling the API directly.</li></ul> | Third-party penetration test (Untested) |

## 3. Persona scenarios (browser, real stack)

| Persona | Scenario | Path | Result |
|---|---|---|---|
| **Business owner** (Mama Nkechi's Kitchen) | A1: Onboarding; wrong password shows an error | Success + failure | Pass (found BUG-08) |
| | A2: Forgot password → email link → mismatched passwords caught → reset → old session signed out | Success + failure | Pass |
| | A3: Free limit reached → clear upgrade message → paid plan unlocks | Failure → success | Pass |
| | A4: Results CSV with one bad row is refused whole; formula text exported safely | Failure | Pass |
| **Social media manager** (agency, 2 clients) | B1: Agency with two clients; editor added to client 1 only | Success | Pass |
| | B2: Editor sees only her client; the other is closed to her | Failure (access) | Pass |
| | B3: Editor can't connect accounts or approve, and is told why | Failure (role) | Pass |
| | B4: Cross-site request without our header is blocked | Attack | Pass |
| **Freelancer** (Chịamaka, Igbo name) | C1: Profile; portfolio PDF with a Unicode filename uploads and downloads | Success | Pass (found BUG-02) |
| | C2: A program disguised as a PDF is refused with a clear message | Failure | Pass |
| | C3: CV with an Igbo title exports as HTML and text | Success | Pass (BUG-02) |
| | C4: Change password keeps this device signed in | Success | Pass |
| **Remote job seeker** (Musa, Kano, on a phone) | D1: Onboarding on a phone: required fields enforced, no sideways scroll | Failure → success | Pass |
| | D2: US-only Remotive role flagged "not eligible"; listing stays unverified | Failure (eligibility) | Pass |
| | D3: Keyboard-only sign-in (Tab + Enter) | Accessibility | Pass |

The four earlier happy-path suites (52 steps) also ran green in the final regression.

## 4. Bugs (all fixed and regression-tested)

| ID | Sev | Bug | How it was found and reproduced | Fix | Regression test |
|---|---|---|---|---|---|
| BUG-14 | **High** | Free limit overrun by parallel requests: at 29/30 used, 6 simultaneous generations all succeeded | `asyncio.gather` of 6 sends → `[201×6]` | Free-plan check locks the org's monthly usage row until the request commits | `test_free_limit_holds_under_concurrent_requests` (5/5 repeats) |
| BUG-08 | **High** | A wrong password silently reloaded the sign-in page with empty fields: no error shown | Persona A1; network trace showed the 401 being treated as an expired session | Sign-in and recovery calls don't redirect on 401 | Persona A1 |
| BUG-03 | **High** | No account recovery at all, although the lockout message says "reset your password"; sessions survived a password change | Area 1 review | Forgot/reset/change password; old tokens invalidated; refresh tokens revoked; lockout cleared; throttled; no enumeration; honest 503 if no email service | `tests/qa/test_recovery.py` (7), personas A2, C4 |
| BUG-02 | **High** | Download and all exports crashed (500) for non-Latin names, e.g. "Chịamaka Ọkafọ CV.pdf" | Unicode upload → download returned 500 | RFC 6266 `Content-Disposition` with an ASCII fallback plus a UTF-8 name | `test_unicode_filename_upload_and_download`, `test_unicode_titles_export`, personas C1, C3 |
| BUG-01 | Medium | Two simultaneous currency conversions: the second returned 500 (cache insert collision) | Baseline integrations step 8 failed | Upsert, so one fetch serves both | `test_concurrent_cache_misses_fetch_once_and_never_500` |
| BUG-05 | Medium | Open redirect after sign-in: `/login?next=/\evil.example` led to another site | Redirect probe in real Chromium | `safeNext()` resolves against our own origin (sign-in and OAuth callback) | Redirect probe + personas |
| BUG-06 | Medium | Calendar month bar overflowed 30px at 360px (sideways scroll on phones) | Sweep X1 | Wraps; responsive width | Sweep X1 |
| BUG-07 | Medium | Colour contrast below WCAG AA on all three dashboard heroes | axe (X2) | Full-opacity text; darker outlined buttons | Sweep X2 |
| BUG-10 | Medium | Audit log recorded our web server (127.0.0.1) for every event, never the person's IP or device | Inspected `audit_events` after the persona run | Real client IP via trusted proxies only; unknown is stored as unknown; web server forwards the user agent | `test_client_ip_resolution`, `test_audit_records_the_person_not_our_server` |
| BUG-11 | Medium | No per-IP throttling on sign-in, sign-up or reset (credential stuffing, bulk sign-ups) | Area 13 review | Per IP: 30 failed sign-ins/15 min, 10 sign-ups/h, 10 resets/h; 429 + Retry-After | 3 tests in `test_gaps.py` |
| BUG-12 | Medium | No Content-Security-Policy on the web app | Header check | Per-request nonce CSP: `strict-dynamic`, no framing, same-site fetches/forms, no plugins | Sweep X5 (0 violations on 22 pages) |
| BUG-04 | Low | ICS export kept bare carriage returns (malformed lines in some calendar apps) | Export review | Line breaks normalised | `test_calendar_exports_neutralise_formulas_and_header_injection` |
| BUG-09 | Low | Personal API responses had no `Cache-Control` | `test_api_security_headers` | `no-store` on every API response | Same |
| BUG-13 | Low | Every tab (all divisions and sign-in) was titled "Creator & Marketing" | Metadata review | Neutral root title; "Page · Workspace · Product" | Sweep X5 |

## 5. Blocked and untested

**Blocked:** couldn't run here.

| Item | Why | What's needed |
|---|---|---|
| Live AI output quality (`tests/evals`, 1 skipped) | No model API key; no internet | Set `ECO_LIVE_EVALS=1` with a key and run the golden cases |
| Real email delivery (reset links) | No email provider configured; flow verified via the dev outbox | Choose a provider; send a real reset to a real inbox |
| Live Google/YouTube, Remotive, ExchangeRate-API | No internet | The go-live checklist in `docs/INTEGRATIONS.md` |
| Firefox and Safari (WebKit) | Only Chromium is installed | Run the browser suites on both |

**Untested:** not attempted.
- Screen readers (NVDA, VoiceOver, TalkBack).
- Real phones and tablets.
- Multi-instance deployment: the rate limiters are in-process.
- Long soak or stress beyond 100 users.
- Backup and restore.
- Paystack checkout (not built).
- An external penetration test.

## 6. Risks and recommendations (not bugs)

1. **Rate limiters are per process** (sign-in/sign-up, integrations). Run one API instance, or move them to Redis, before scaling out.
2. **Capacity:** one API worker handled about 96 requests/second with 0 errors. p95 latency was 0.9s at 50 users and 1.6s at 100 users, from queueing. Run several workers (for example, CPU count) in production and repeat the load test there.
3. **The CSP still allows inline styles** (needed by React style attributes). Scripts are nonce-only. The CSP makes every page render per request; the measured cost was negligible (every page settled within 1.1s locally).
4. **Free-plan generations queue per organisation** (the BUG-14 fix): one at a time for Free orgs only. Paid plans are unaffected.
5. **Set the deployment settings for real client IPs:** `TRUST_FORWARDED_FOR=true` on the web server and the load balancer's address in the API's `TRUSTED_PROXIES`. Without them, IPs are recorded as unknown and per-IP limits don't apply; per-account lockout still does.

## 7. How to rerun

```bash
# backend (needs PostgreSQL)
cd eco-backend && python -m pytest -q          # 296 tests
python -m tests.e2e_server &                    # real API + fresh DB on :8000 (fake AI and providers)
# web
cd eco-web && npm run build && API_URL=http://127.0.0.1:8000 npx next start -p 3000 &
for f in run business freelancer integrations personas; do node e2e/$f.mjs; done
# after the browser suites (they fill the DB with other tenants' data)
cd eco-backend && python -m tests.qa.idor_sweep && python -m tests.qa.load 100 30
```

The bug log with one line per bug is in `docs/qa/bugs.md`.
