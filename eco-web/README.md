# New Age AI: web app

New Age AI is a product of New Age Media. Installable on phones (web app manifest + an offline-screen service worker).

Next.js 15 (App Router) + TypeScript + Tailwind 3, styled with the New Age AI design system (cream canvas, black
frame, orange actions; Bricolage Grotesque, Instrument Sans, JetBrains Mono). Talks to `eco-backend`.

What each feature does, and what still needs integrations: `eco-backend/docs/CREATOR.md`, `BUSINESS.md` and `FREELANCER.md`.
Each division plugs into one shell (`src/components/divisions.ts`): its own nav, accent, workspace list and product check.

## Security model

- **No tokens or keys in the browser.** Sign-in goes through `/api/auth/*`, which stores the access token and the
  rotating refresh token in **httpOnly** cookies (refresh token scoped to `/api`, SameSite=Strict).
- Every API call goes through the same-origin proxy `/api/proxy/v1/...`. It adds the bearer token, refreshes once
  on 401, only reaches `/v1/*` (never `/v1/auth/*`), caps uploads, and passes back a fixed set of headers.
- **CSRF:** mutating requests need the `x-eco-csrf: 1` header and a same-origin `Origin`; cross-site forms can't add either.
- `API_URL` is server-only. The browser test checks the built bundles contain no API address or secret names.
- AI and user text are rendered as React text nodes (a small safe Markdown renderer), never as raw HTML. Only `http(s)`
  links become clickable, and they open with `noopener noreferrer nofollow`.
- Security headers: `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, a restrictive `Permissions-Policy`.

## Run it

```bash
npm ci
cp .env.example .env.local      # API_URL=http://localhost:8000 ; COOKIE_SECURE=true behind HTTPS
npm run dev                     # http://localhost:3000
npm run build && npm run start:prod   # production (standalone server, as in the Docker image)
```

## Screens

Sign up / sign in · onboarding (solo or agency, first client, audience and voice) · all clients (with profile
completeness) · per client: dashboard, assistant, studio, calendar, campaigns (+ detail), library (editor with
versions and comments), approvals (+ client review links), brand & audience, research, reports, settings
(integration status, access) · public client review page (`/review/{token}`).

**Business Marketing:** product chooser (`/start`) · 6-step onboarding (`/business/onboarding`) · all businesses ·
per business (`/b/{id}`): dashboard, strategist chat, strategy tools (10, config-driven), campaigns, saved work by
project (editor with versions and exports), approvals, results & reports, profile & intelligence (editable), settings.

**Freelancer Growth:** 6-step onboarding (`/freelancer/onboarding`) · per person (`/f/{id}`): dashboard (local
time, follow-ups), career assistant, opportunities (eligibility, time-zone overlap, red flags, verify at source),
applications tracker, CV & resume, letters & proposals, interview prep and practice, services & pricing, outreach,
portfolio, personal brand, profile & skills assessment, learning plan, saved work + uploaded files, resources
(checked directory, CV norms by country, rate calculator), settings.

Layout follows the design system: 248px black sidebar on desktop, drawer + bottom navigation on phones, 44px+
touch targets, visible focus rings, reduced-motion respected, light and dark themes from the same tokens.

## End-to-end test

Real browser, real web app, real API and Postgres; only the LLM is scripted (inside the test API server).

```bash
# terminal 1 (eco-backend): fresh `eco_e2e` database + API on :8000 (test-only server)
python -m tests.e2e_server
# terminal 2 (eco-web)
npm run build && API_URL=http://127.0.0.1:8000 PORT=3000 npm run start:prod
# terminal 3
node e2e/run.mjs                # Creator: 16 workflows; screenshots in e2e/out/
node e2e/business.mjs           # Business: 13 workflows; screenshots in e2e/out/business/
node e2e/freelancer.mjs         # Freelancer: 14 workflows; screenshots in e2e/out/freelancer/
node e2e/integrations.mjs       # Integrations: 9 steps (YouTube OAuth, Remotive, exchange rates)
node e2e/personas.mjs           # QA: 4 personas + consent/data rights, success and failure paths, then an
                                # brand + install checks, then an axe accessibility / 360px / CSP / title / speed sweep over 25 pages (26 checks)
```

The test API server also fakes the integration providers; nothing reaches the internet. Playwright isn't a project
dependency: install `playwright@1.63.0` and its Chromium to run these (CI does).

## Brand and installable app

- Logo and icons come from the New Age AI logo (`public/brand/new-age-ai-logo.png`): the orange "AI." mark on black
  is the app icon (`public/icons/`, incl. a maskable icon for Android). `src/components/Logo.tsx` is the wordmark.
- `src/app/manifest.ts` serves `/manifest.webmanifest` (name, standalone display, start URL `/start`, icons).
- `public/sw.js` only shows `/offline` when a page can't load. It caches the offline screen and two icons, nothing
  else: no pages, API responses or files, so no account data is stored on the device (checked by a browser test).
- Manifest, icons, `sw.js` and `/offline` are public (no sign-in) so installing works from the sign-in page.
- The standalone build does not include `public/`; `npm run start:prod` and the Dockerfile copy it.

## Legal pages and data rights

- `/privacy` and `/terms` render `src/content/legal/*.md` (a small safe Markdown subset, no raw HTML). Both files start
  as drafts with a `<!-- DRAFT … -->` first line and show a "Draft for legal review" banner.
- `node scripts/check-legal.mjs` exits 1 while a draft marker or a `[PLACEHOLDER]` remains; the production pipeline
  runs it and refuses to deploy until counsel-approved text is in place.
- Sign-up requires ticking "I agree to the Terms of Service and Privacy Policy" (the API stores the version and time).
- Settings → Your data: "Download my data" (JSON export) and "Delete my account" (password + typing DELETE).

## Production build

`next.config.mjs` builds a standalone server (`output: "standalone"`). The `Dockerfile` runs it as a non-root user;
it copies `.next/static` and `src/content` next to `server.js`. Runtime settings: `API_URL`, `COOKIE_SECURE=true`,
`TRUST_FORWARDED_FOR=true` behind the host's proxy, `NOINDEX=true` on staging only. Pages render per request (each
carries its own CSP nonce).

## Security headers

Every page gets a Content-Security-Policy with a fresh nonce per request (`src/middleware.ts`): only scripts this
server rendered run; no framing (`frame-ancestors 'none'`); fetches and forms stay on this site; fonts from Google
Fonts only. Pages therefore render per request. Plus `X-Frame-Options`, `nosniff`, `Referrer-Policy` and
`Permissions-Policy` from `next.config.mjs`. The browser QA suite (`e2e/personas.mjs`, X5) checks the policy is
present and causes no violations on 22 pages.
