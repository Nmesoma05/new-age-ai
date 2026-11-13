# New Age AI API: backend and database

New Age AI is a product of New Age Media.

FastAPI + PostgreSQL backend for the three-division AI SaaS: Creator & Marketing, Business Marketing and Freelancer Growth.
Tenant isolation is enforced twice: in application code (role checks per endpoint) and in the
database (row-level security). The API connects as a role that cannot bypass RLS.

- Schema and relationships: [`docs/ERD.md`](docs/ERD.md)
- Endpoints, errors, pagination, plan rules: [`docs/API.md`](docs/API.md), plus [`docs/openapi.json`](docs/openapi.json)
- Intelligence engine (agents, tools, memory, safety, evals): [`docs/AI_ENGINE.md`](docs/AI_ENGINE.md)
- Creator & Marketing division (features, what's operational vs. integration-required, workflows): [`docs/CREATOR.md`](docs/CREATOR.md)
- Business Marketing division (same, plus the integrations still to build): [`docs/BUSINESS.md`](docs/BUSINESS.md)
- Freelancer Growth division (same, plus global/African support and honesty rules): [`docs/FREELANCER.md`](docs/FREELANCER.md)
- External integrations (implemented vs planned, OAuth/token handling, approvals, test plan, sources): [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md)
- Migrations: [`migrations/versions/`](migrations/versions) (`0001_core_schema`, `0002_rls_policies`, `0003_ai_engine`, `0004_creator`, `0005_business`, `0006_freelancer`, `0007_integrations`, `0008_account_recovery`, `0009_launch`)

## Layout

```
app/
  core/       config (+ deployed-environment guards), db sessions + tenant context, auth/JWT, RBAC maps, errors,
              pagination, crypto, observability (JSON logs, Sentry), client IP, per-IP rate limits
  api/ops.py  /health and /ready
  models/     SQLAlchemy models (mirror the migrations; a test checks they match)
  schemas/    Pydantic request/response models (validation)
  services/   accounts, billing/entitlements, subscriptions, storage + scanning, audit, recovery, privacy, mailer
  integrations/ outbound HTTP client (allowlist, retries, breaker, call log), OAuth + token vault, catalog, providers
  ai/         intelligence engine: providers/, agents/, tools, retrieval, memory, safety, ingest, orchestrator
  api/v1/     routers: auth, orgs, workspaces, profiles, documents, content, assistant, creator, business, freelancer, integrations, billing, admin
migrations/   Alembic, raw SQL
scripts/      create_roles.sql, export_openapi.py; ops: predeploy, migration_safety, backup, restore_drill,
              purge_deleted, smoke, activate_plan (see "Deployment and operations")
evals/       golden cases for live-model evaluation
tests/        332 tests run against a real Postgres database with RLS active (+ live evals, skipped without a key)
```

## Setup

Requires Python 3.12+ and PostgreSQL 15+ with **pgvector** (tested on 16 with pgvector 0.6; uses `citext`, `vector`,
`ON DELETE SET NULL (col)`). Self-hosted: install your distro's pgvector package (e.g. `postgresql-16-pgvector`);
`create_roles.sql` enables it. Supabase: enable the `vector` extension in the dashboard.

```bash
pip install -r requirements-dev.txt
cp .env.example .env            # fill in secrets; see comments in the file
psql -U postgres -v owner_password=... -v app_password=... -f scripts/create_roles.sql
                                # creates eco_owner (owns tables), eco_app (NOBYPASSRLS) and database eco
alembic upgrade head            # runs as MIGRATIONS_DATABASE_URL (eco_owner)
uvicorn app.main:create_app --factory --reload
```

Passwords are passed as psql variables, so none are stored in the script. The test suite also needs `eco_owner` to have `CREATEDB`
(`ALTER ROLE eco_owner CREATEDB;` on a dev machine only), and pgvector enabled in `template1` so each throwaway test
database has it (`psql -U postgres -d template1 -c 'CREATE EXTENSION vector'`).

## Deployment and operations

Production setup, the go-live checklist and the rollout plan are in the ops kit (`LAUNCH_PLAN.md`, `render/`,
`.github/workflows/`, `runbooks/`). What lives here:

| Piece | What it does |
|---|---|
| `Dockerfile` | Production image (Python 3.13, non-root, Postgres 16 client tools for backups). Starts `uvicorn` with `WEB_CONCURRENCY` workers and `--no-proxy-headers` (client IPs come from `TRUSTED_PROXIES` only) |
| `ENV=staging` / `prod` | Startup guards: refuses a Paystack test key in prod (live key in staging), local storage, no SMTP, non-https URLs, no `AI_DAILY_BUDGET_USD`, $0 `AI_MODEL_PRICES`, no `LEGAL_TERMS_VERSION`, scanning off |
| `/health`, `/ready` | Liveness (+ release) and readiness (database + schema at head, storage, scanner) |
| `python -m scripts.predeploy` | The host's pre-deploy command: migration safety gate → backup if migrations are pending → `alembic upgrade head`. Failure aborts the deploy |
| `python -m scripts.migration_safety --since <rev>` | Refuses destructive migrations (drop, rename, type change, NOT NULL…) unless `ALLOW_DESTRUCTIVE_MIGRATION=<rev>` |
| `python -m scripts.backup` | `pg_dump` + manifest (schema, row counts, sha256) to `BACKUP_S3_BUCKET`, prunes after 35 days |
| `python -m scripts.restore_drill` | Restores the latest backup into a scratch database and checks it against the manifest, RLS and grants |
| `python -m scripts.purge_deleted --apply` | Daily: erases organisations closed by account deletion after 30 days, files first |
| `python -m scripts.smoke --mode staging\|production` | Post-deploy checks through public URLs; staging runs the full journey with a throwaway account |
| `python -m scripts.activate_plan` | Manual, audited plan activation for invoiced beta customers until Paystack checkout ships |

## Tests

```bash
export TEST_PG_HOST=localhost TEST_PG_OWNER=eco_owner TEST_PG_OWNER_PASSWORD=... TEST_PG_APP_PASSWORD=...
pytest -q
```

The suite creates a throwaway database, migrates it and drops it afterwards. Requests go through the real app, the real database
connection as `eco_app`, and real RLS. The only test double is the external LLM (`tests/ai/scripted.py`), which records
exactly what a model would have been shown and can play an honest or a compromised model. Every row
the tests assert on is read back from Postgres.

| File | Covers |
|---|---|
| test_auth.py | signup, login, lockout, refresh rotation and reuse detection, logout, token tampering, unknown email gets the same error as a wrong password |
| test_isolation.py | cross-tenant reads/writes return 404 across orgs, workspaces, documents, assets, conversations |
| test_permissions.py | org and workspace roles: viewer read-only, editor limits, admin-only approve, member visibility, owner protection |
| test_rls_db.py | direct SQL as `eco_app`: RLS hides other tenants even without the API; app role owns nothing; audit is append-only |
| test_usage_billing.py | Free 30/month limit, paid unlimited, failed calls not counted, cancel to period end, renewal, downgrade read-only, fair use, rate limit |
| test_documents.py | upload, type sniffing, macro DOCX rejection, size limit, unscanned files blocked, signed URL tampering, tenant-prefixed keys |
| test_content.py | conversation round-trip with usage record + saved asset, history order, asset versions/status, cursor pagination, profile versioning |
| test_audit_integrations_webhooks.py | audit trail, encrypted integration credentials, webhook signature and idempotency |
| test_migrations.py | models match the migrated schema; upgrade → downgrade → upgrade |
| integrations/ | outbound HTTP client, OAuth/PKCE and tokens, YouTube sync, exchange rates, Remotive, approval executor contract |
| qa/ | security probes, account recovery, gaps (seats, grace period, hostile bodies, headers, per-IP limits, Free-limit race); `idor_sweep.py` and `load.py` run against the e2e server |
| launch/ | readiness, deployed-environment guards, AI daily budget, SMTP, terms acceptance, export, deletion + purge, S3 storage, scanner protocol, JSON logs, shared limits, manual activation, `.env.example` completeness |
| ai/test_providers.py | OpenAI and Anthropic wire formats, refusals, bad JSON, retries, fail-closed without keys |
| ai/test_safety_retrieval_memory.py | injection detection, output scrubbing, txt/docx/pdf extraction, retrieval isolation, private and quote-grounded memory |
| ai/test_tools.py | tool gates (allowlist, role, strict args, no tenant ids), scoping, taint, proposals |
| ai/agents/test_00…07 | registry limits, then each agent on its own: router, assistants, content writer, AIDA strategist, proposal writer, document analyst, researcher |
| ai/test_orchestrator.py | full multi-agent pipeline over HTTP, clarify/unsupported, fallback, rollback, memory across turns, summaries |
| ai/test_adversarial.py | compromised-model evals: cross-tenant canaries, document injection end to end, memory poisoning, tenant smuggling |
| ai/test_actions_memory_api.py | approval workflow, expiry, spend approval by org admin, memory lifecycle and privacy |
| evals/test_live_evals.py | real-model golden cases (`ECO_LIVE_EVALS=1` + API key); security cases must be 100% |

## Security notes

AI-specific safeguards (prompt injection, memory isolation, approval-gated actions) are in docs/AI_ENGINE.md §6.


- **Secrets stay on the server.** OpenAI/Anthropic, Paystack, JWT and encryption keys are read only from environment
  variables as `SecretStr`, never logged, never returned. The frontend never needs any of them: it calls this API with the
  user's bearer token.
- **Passwords**: argon2id. An unknown email still runs a hash, so response timing doesn't reveal which accounts exist.
- **Tokens**: 15-minute access JWT. Refresh tokens are stored only as SHA-256 hashes; reuse of a rotated token revokes the family.
- **RLS**: `eco_app` is `NOBYPASSRLS` and owns no tables. Billing tables are writable only inside a server-opened system context.
- **Not found, not forbidden**: records in another tenant return 404, so IDs can't be probed.
- **Uploads**: content type comes from magic bytes; allow-list; DOCX with macros rejected; size capped while streaming;
  virus-scanned (ClamAV) before download is allowed; storage keys are server-generated and tenant-prefixed;
  downloads go through short-lived signed tokens and are served as `attachment` with `nosniff`.
- **Integrations**: credentials are Fernet-encrypted at rest, never returned, and overwritten on revoke.
- **Audit log**: append-only (trigger + grants); secret-looking keys are redacted from metadata.
- **Production guards**: the app refuses to start with `ENV=prod` and the file scanner disabled, wildcard CORS, or an
  incomplete external-JWT config. Interactive docs are disabled in prod.

## Known limitations and next steps

- Under heavy concurrency, the Free-plan check and increment are not one atomic step, so an org could go 1–2 generations over 30.
  To close this, move the check into a single conditional `UPDATE … WHERE free_generations_used < limit`.
- A file is written to storage before the database commit. If the commit fails, an orphaned object is left behind; a periodic sweep should remove it.
- Not built yet: MFA, email verification, invitations, client-approver per-item grants, `Idempotency-Key` handling,
  background workers (subscription expiry, document ingestion and summaries currently run inline), a web research
  backend, and executors for approved external actions (see docs/AI_ENGINE.md §10).
- Written but not exercised against the live services: S3 backend, ClamAV, the OpenAI and Anthropic adapters and embeddings
  (wire formats tested with a mock transport only; live evals not yet run), external JWT with Supabase, and the Paystack
  payload mapping (signature check is implemented; confirm event fields against Paystack's current docs before launch).
- Integrations store credentials only; no third-party API is called yet.
