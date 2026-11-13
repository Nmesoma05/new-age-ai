# New Age AI

**A product of New Age Media.** AI for creators and agencies (Creator & Marketing), business owners (Business
Marketing), and freelancers and job seekers (Freelancer Growth): one account, separate workspaces.

| Folder | What it is |
|---|---|
| `eco-backend/` | API: FastAPI + PostgreSQL 16 (row-level security per workspace), AI engine, integrations, tests. See its README |
| `eco-web/` | Web app: Next.js 15, installable on phones. See its README |
| `.github/workflows/` | CI (tests, browser suites, security checks), deploy to staging, promote to production |
| `render/` | Render Blueprints for staging and production |
| `ops/`, `runbooks/` | Deploy scripts; deploy/rollback, incident, disaster-recovery and secrets runbooks (see `OPS.md`) |
| `LAUNCH_PLAN.pdf` | Launch-readiness plan, go-live checklist, risks and phased rollout |

## Run it on your computer

Needs Python 3.13, Node 22 and PostgreSQL 16 with pgvector.

```bash
# API with a fresh test database, a scripted (offline) AI and fake integrations, on :8000
cd eco-backend && pip install -r requirements-dev.txt && python -m tests.e2e_server
# web app on :3000 (second terminal)
cd eco-web && npm ci && npm run build && API_URL=http://127.0.0.1:8000 PORT=3000 npm run start:prod
```

Then open http://localhost:3000. Real AI, email, file storage and payments need the settings in
`eco-backend/.env.example` (never commit real keys).

## Status

Built and tested: three divisions, AI engine, integrations framework (YouTube analytics, Remotive jobs, exchange
rates), account recovery, data export and deletion, QA and security suites (332 backend tests, 78 browser steps).
Not built yet: Paystack checkout, the Telegram/WhatsApp bots, store apps. Legal pages are drafts for review.
