# Technical decisions

Newest first. Status: **approved**, **awaiting approval** (made during a task, reversible, flagged to the product
owner), or **superseded**.

| Date | Decision | Why | Status |
|---|---|---|---|
| 2026-11-13 | Brand: the whole ecosystem is **New Age AI, a product of New Age Media**; the three divisions stay as its sections | Product owner's decision | approved |
| 2026-11-13 | Channels, built one at a time on the same backend: installable web app → Telegram bot → WhatsApp bot → native apps | Product owner wants every channel; order by cost and readiness | approved (order proposed) |
| 2026-11-13 | Exports and client review pages are NOT stamped with the New Age AI brand | Agencies hand them to their own clients; branding them is a product decision | awaiting approval |
| 2026-11-13 | Service worker shows an offline screen only; caches no pages, API data or files | No account data on shared or lost phones | approved (this task) |
| 2026-11-13 | Next.js `htmlLimitedBots: /.*/` (page metadata sent up front, not streamed) | Streamed metadata could overwrite the page title after load | approved (this task) |
| 2026-11-13 | `wrong_password` is always HTTP 400 (account deletion used 403) | One code, one status, so clients handle it once | approved (docs task) |
| 2026-11-13 | Web app runs as the Next.js standalone server everywhere (tests, CI, Docker), via `npm run start:prod` | `next start` is unsupported with `output: standalone`; test what ships | approved (docs task) |
| 2026-11-13 | `ENV=staging` with every production guard | Staging proves production's configuration | awaiting approval |
| 2026-11-13 | Per-IP sign-in/sign-up/reset limits stored in Postgres (`auth_attempts`), not memory | Limits must hold across workers and instances; no Redis needed | awaiting approval |
| 2026-11-13 | Hosting recommendation: Render, Frankfurt, images built by GitHub Actions | pgvector, pre-deploy command, PITR; nearest region to Nigeria on Render. Must verify the restricted DB role on day 1 | awaiting approval |
| 2026-11-13 | Account deletion: anonymise the person at once; erase solely-owned organisations (files included) after 30 days; keep work done in other organisations' workspaces, credited to "Deleted user" | Erasure right vs. agencies' own records; 30-day grace for mistakes | awaiting approval |
| 2026-11-13 | Draft privacy policy and terms in the repo, blocked from production by a release gate until counsel approves | Product must show real policies; drafts must never ship as final | awaiting approval |
| 2026-11-13 | Migrations are additive only (expand/contract), enforced by `scripts/migration_safety` | Old code keeps working during deploys and after rollbacks | awaiting approval |

## Private preview on Render (ENV=preview), 2026-11-21 — awaiting approval of spend
- New `ENV=preview`: counts as deployed (https, JSON logs, API docs hidden, AI daily budget + model prices required)
  but allows `UPLOADS_ENABLED=false` (then local storage and no scanner are accepted), `EMAIL_BACKEND=none`, and
  requires `SIGNUP_ALLOWLIST`. staging and prod keep every guard (tested).
- `render/preview.yaml`: Postgres 16 (basic-256mb), the API as a **private service** (no public URL), the web as the
  only public service. Render builds from the Dockerfiles in this repo.
- Database roles: Render's default user (not a superuser) is the owner and runs migrations; `scripts/render_start.py`
  creates the restricted `eco_app` role (checked: no superuser/BYPASSRLS/CREATEROLE) and starts the API as eco_app.
- No backups beyond what Render's plan provides; no uploads, so no file storage to back up.
- Blank secret fields (e.g. OPENAI_API_KEY left empty in the dashboard) mean "not configured".
