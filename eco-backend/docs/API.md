# API reference (v1)

The machine-readable contract is `docs/openapi.json`, generated from the code with
`python scripts/export_openapi.py`. In `dev` the interactive docs are served at `/docs`. They are
switched off when `ENV=prod`.

## Conventions

**Base path** `/v1`. JSON in and out, except uploads (`multipart/form-data`) and file downloads.

**Authentication.** `Authorization: Bearer <access token>`.
- `AUTH_MODE=local`: tokens come from `/v1/auth/login` or `/v1/auth/signup`. Access tokens are HS256 JWTs and last 15 minutes.
  Refresh tokens are opaque, last 30 days and rotate on every use. Presenting an already-used refresh token
  revokes its whole family. Ten failed logins lock the account for 15 minutes (`429 account_locked`).
- `AUTH_MODE=external_jwt`: send the identity provider's JWT instead. It is verified against `EXTERNAL_JWKS_URL`, issuer and
  audience, and a local user is provisioned on first sight. The local signup, login, refresh and logout routes return 404 in this mode.

**Errors** are RFC 9457 `application/problem+json`. Branch on `code`, not on `title`:

```json
{ "type": "about:blank", "title": "Free limit reached", "status": 402,
  "code": "free_limit_reached", "detail": "…", "request_id": "6f1c…" }
```

Validation failures are `422 validation_failed`, with an `errors` array of `{loc, msg, type}`.
Every response carries `X-Request-ID`. A record you can't access returns `404 not_found`, the same response as a
record that doesn't exist, so IDs from other tenants can't be probed.

**Pagination.** List endpoints take `?limit=` (1–100; default 25, messages 50) and `?cursor=`, and return
`{"data": [...], "next_cursor": "…" | null}`. Results are newest first and ordered by `(created_at, id)`, so pages
never repeat or skip rows while new rows are inserted.

**Security headers** on every response: `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`.
Add HSTS, frame and cache headers at the edge proxy or CDN.

## Roles

| Organisation role | Can |
|---|---|
| owner | everything, including delete and transfer; can't be removed |
| admin | manage members, teams, products, integrations, all workspaces; read audit log |
| billing | read subscription and usage |
| member | sees only the workspaces they are added to |

| Workspace role | Can |
|---|---|
| admin | manage workspace members; approve assets |
| editor | create and edit content, documents, conversations, profiles |
| viewer | read only |
| client_approver | reserved for per-item client review; no general access yet |

## Endpoints

### Auth and account
| Method | Path | Notes |
|---|---|---|
| POST | /v1/auth/signup | `{email, password (10–128 chars), display_name, product?, accept_terms}`. Creates the user and a personal org (on Free until a subscription is activated); returns tokens. When `LEGAL_TERMS_VERSION` is set (always, when deployed) `accept_terms: true` is required (`422 terms_required`) and the version + time are stored. Per-IP limit: `SIGNUP_IP_PER_HOUR` |
| POST | /v1/auth/login | `{email, password}` → `{access_token, refresh_token, expires_in}`. Per-account lockout plus per-IP failure limit (`LOGIN_IP_MAX_FAILURES` per 15 min, shared across instances) |
| POST | /v1/auth/refresh | `{refresh_token}` → new pair; reuse revokes the family |
| POST | /v1/auth/logout | `{refresh_token}` → 204 |
| POST | /v1/auth/password/forgot | `{email}` → 202 with the same answer whether or not the account exists. Emails a single-use link valid 30 min (max 3/hour per account, `FORGOT_IP_PER_HOUR` per IP). `503 email_not_configured` when no email backend is set |
| POST | /v1/auth/password/reset | `{token, new_password}`. Single use; signs out every session; clears lockout. `400 reset_link_invalid`, `422 password_reused` |
| POST | /v1/me/password | `{current_password, new_password}`. Signs out other sessions and returns fresh tokens for this one. `400 wrong_password` |
| GET / PATCH | /v1/me | Profile: display name, locale, timezone, country, currency |
| GET | /v1/me/export | Right of access/portability: one JSON file (`Content-Disposition: attachment`) with account, memberships, professional profiles, memories, conversations (both sides), content + versions, document metadata, opportunities, applications, interview sessions and own audit activity. No hashes, tokens, embeddings or storage keys |
| POST | /v1/me/delete | `{password, confirm: "DELETE"}`. Signs out everywhere, anonymises the account (name, email, password removed), deletes memories and professional profiles, ends memberships elsewhere, closes organisations the person solely owns; `scripts/purge_deleted.py` erases those (files included) after `PURGE_AFTER_DAYS` (30). `400 wrong_password`, `409 transfer_ownership_first` (owns a team others use; `organisations` listed), `409 cancel_subscription_first` (auto-renewing paid plan) |

### Organisations, members, teams, products
| Method | Path | Notes |
|---|---|---|
| GET / POST | /v1/orgs | List mine / create a team org (caller becomes owner) |
| GET / PATCH | /v1/orgs/{org_id} | |
| GET / POST | /v1/orgs/{org_id}/members | Add an existing user by email; seat limit from plan; not allowed in personal orgs |
| PATCH / DELETE | /v1/orgs/{org_id}/members/{user_id} | Owner is protected |
| GET / POST | /v1/orgs/{org_id}/teams | |
| POST | /v1/orgs/{org_id}/teams/{team_id}/members | |
| GET / POST | /v1/orgs/{org_id}/products | Enable creator, business or freelancer (freelancer only on personal orgs) |

### Workspaces and projects
| Method | Path | Notes |
|---|---|---|
| GET / POST | /v1/orgs/{org_id}/workspaces | Create needs product access and is under the plan's workspace limit; list shows `read_only` |
| GET / PATCH / DELETE | /v1/workspaces/{workspace_id} | Delete is a soft delete, owner only |
| GET / POST | /v1/workspaces/{workspace_id}/members | Not allowed on freelancer workspaces |
| PATCH / DELETE | /v1/workspaces/{workspace_id}/members/{user_id} | |
| GET / POST | /v1/workspaces/{workspace_id}/projects | |
| PATCH | /v1/workspaces/{workspace_id}/projects/{project_id} | |

### Division profiles (each `PUT` upserts and bumps `version`)
| Method | Path | Product |
|---|---|---|
| GET / PUT | /v1/workspaces/{id}/client-account | creator |
| GET / PUT | /v1/workspaces/{id}/business-profile | business |
| GET / PUT | /v1/workspaces/{id}/professional-profile | freelancer |

Using the wrong product's profile on a workspace returns `409 wrong_product`.

### Documents
| Method | Path | Notes |
|---|---|---|
| POST | /v1/workspaces/{id}/documents | Multipart `file`, optional `project_id`. Max `MAX_UPLOAD_BYTES` (default 20 MB). Type is sniffed from bytes. Allowed: PDF, DOCX (no macros), plain text, PNG, JPEG. Scanned before it becomes downloadable |
| GET | /v1/workspaces/{id}/documents | Paginated |
| GET / DELETE | /v1/workspaces/{id}/documents/{doc_id} | Delete is soft |
| POST | /v1/workspaces/{id}/documents/{doc_id}/download-url | Short-lived signed URL (default 15 min); only for `scan_status = clean` |
| GET | /v1/files/{token} | Streams the file as `attachment` with `nosniff`; any tampering or deleted file → 404 |

### Conversations and saved outputs
| Method | Path | Notes |
|---|---|---|
| GET / POST | /v1/workspaces/{id}/conversations | |
| GET | /v1/workspaces/{id}/conversations/{conv_id}/messages | Paginated, newest first |
| POST | /v1/workspaces/{id}/conversations/{conv_id}/messages | `{content, agent?, document_ids?, save_as_asset?, asset_type?}`. Runs the intelligence engine (routing, agents, tools, validation) server-side and returns `{user_message, assistant_message, run}`. `run` = `{id, agent, status (succeeded/clarify/unsupported), output (structured), warnings, uncertainties, injection_detected, pending_actions, saved_asset_id, memory_saved}`. Needs workspace editor. See [AI_ENGINE.md](AI_ENGINE.md) |
| GET / POST | /v1/workspaces/{id}/assets | Filters: `status`, `tag` |
| GET / PATCH / DELETE | /v1/workspaces/{id}/assets/{asset_id} | Setting `approved` needs workspace admin |
| GET / POST | /v1/workspaces/{id}/assets/{asset_id}/versions | A new version on an approved asset moves it back to `in_review` |

### Assistant: runs, approvals, memory
| Method | Path | Notes |
|---|---|---|
| GET | /v1/workspaces/{id}/runs | Agent runs, newest first, paginated |
| GET | /v1/workspaces/{id}/runs/{run_id} | One run with routing, output, warnings, taint and every tool call |
| GET | /v1/workspaces/{id}/actions | Proposed external actions; `?status=awaiting_approval\|approved\|rejected\|executed\|failed\|expired` |
| POST | /v1/workspaces/{id}/actions/{action_id}/approve | Workspace admin only (`spend_money` also needs org owner/admin). Runs the registered executor; with none registered: `409 no_executor` and the action stays pending |
| POST | /v1/workspaces/{id}/actions/{action_id}/reject | Workspace admin only; optional `{reason}` |
| GET / POST | /v1/workspaces/{id}/memory | List (`?status=active\|proposed\|archived`) / add `{content, kind, visibility: workspace\|private, project_id?}`. Private memory is visible only to its author |
| PATCH / DELETE | /v1/workspaces/{id}/memory/{memory_id} | Confirm a proposed memory (`{"status":"active"}`), archive it, edit it or delete it |

Agent choices for `agent`: `creator.assistant`, `creator.content_writer` (and the other `creator.*` agents),
`business.assistant`, `business.aida_strategist`, `business.profile_builder`, `business.positioning_strategist`,
`business.market_analyst`, `business.marketing_planner`, `business.ads_planner`, `business.growth_strategist`,
`business.performance_analyst`, `freelancer.assistant`, `freelancer.skills_assessor`, `freelancer.cv_writer`,
`freelancer.interview_coach`, `freelancer.answer_coach`, `freelancer.portfolio_builder`, `freelancer.brand_writer`,
`freelancer.outreach_planner`, `freelancer.pricing_advisor`, `freelancer.learning_planner`,
`freelancer.opportunity_analyst`, `freelancer.proposal_writer`, `shared.document_analyst`,
`shared.researcher` (only those for the workspace's product are accepted).

### Creator & Marketing division
See [CREATOR.md](CREATOR.md) for every endpoint, workflow and what needs platform integrations.

### Business Marketing division
See [BUSINESS.md](BUSINESS.md) for every endpoint, workflow and the integrations still to build.

### Freelancer Growth division
See [FREELANCER.md](FREELANCER.md) for every endpoint, workflow and the integrations still to build.

### Billing and usage
| Method | Path | Notes |
|---|---|---|
| GET | /v1/orgs/{org_id}/subscription | Plan, status, period end, `ai_unlimited` |
| GET | /v1/orgs/{org_id}/usage | Free: `free_used_this_month`, `free_remaining`. Paid: counts are `null` (unlimited) |
| POST | /v1/webhooks/paystack | No bearer auth; verified by HMAC-SHA512 `x-paystack-signature`, idempotent on event id |

### External integrations (see docs/INTEGRATIONS.md)
| Method | Path | Notes |
|---|---|---|
| GET | /v1/integrations/catalog?product= | `{verified_on, implemented[], planned[]}`; each with access, requirements, approval rule, fallback, `configured` |
| GET | /v1/workspaces/{id}/integrations | ws.read. Connection metadata (status, account, last sync/error). Never tokens |
| POST | /v1/workspaces/{id}/integrations/{key}/connect | Org owner/admin. `{return_to}` (site path) → `{authorization_url}` (OAuth + PKCE). Implemented providers only |
| POST | /v1/integrations/oauth/complete | `{state, code \| error}` from the callback page; state is single-use, same user, 10 min → `{connection, return_to}` |
| POST | /v1/workspaces/{id}/integrations/{iid}/sync | ws.write. YouTube: `{start?, end?}` (≤1 year) → counts written |
| DELETE | /v1/workspaces/{id}/integrations/{iid} | Org owner/admin. Revokes at provider (best effort), destroys our copy → `{provider_confirmed, message}` |
| GET | /v1/fx/convert?amount=&from=&to= | Indicative daily rate with attribution; `stale` if served from an old cache |
| GET | /v1/workspaces/{id}/jobs/remotive?q=&category= | Freelancer workspaces. Searches the shared Remotive snapshot (≤4 fetches/day app-wide) |
| POST | /v1/workspaces/{id}/jobs/remotive/import | `{job_id}` → unverified opportunity crediting Remotive. 409 already_saved, 404 job_gone |

### Integrations and audit (org owner/admin)
| Method | Path | Notes |
|---|---|---|
| GET / POST | /v1/orgs/{org_id}/integrations | Older generic record store; credentials encrypted, never returned. Catalog providers are refused (`use_connect_flow`) |
| DELETE | /v1/orgs/{org_id}/integrations/{id} | Revokes and destroys the stored secret |
| GET | /v1/orgs/{org_id}/audit-events | Newest first; `?limit=` 1–200 (default 50); pass the returned `next_cursor` as `?before_id=` |
| GET | /health | Liveness: `{status, release}`. No dependencies checked |
| GET | /ready | Readiness: database reachable and schema at the migration head, file storage read/write, virus scanner answering. `200 {status: ready, checks, release}` or `503` with the failing check names only. Used by the load balancer and the deploy pipeline |

## Plan and usage rules

- **Paid plans** (Starter, Pro, Team): unlimited AI generations while the subscription is active,
  or cancelled but inside the paid period, or `past_due` inside `grace_until`. There are no credits.
- **Free plan**: 30 successful generations per organisation per calendar month (UTC). The 31st returns
  `402 free_limit_reached`. One message = one generation, however many model calls the engine makes for it.
  Failed runs, clarifying questions and "unsupported" answers are recorded but not counted.
- **Fair use** (every plan): more than `AI_RATE_LIMIT_PER_MINUTE` per user returns `429 rate_limited`. Monthly provider cost above
  `FAIR_USE_MONTHLY_USD_PER_USER` returns `429 fair_use_review` for review. Both responses send `Retry-After`.
- **Daily AI budget** (whole service): when today's provider spend across all organisations reaches
  `AI_DAILY_BUDGET_USD`, new generations return `503 ai_paused` until midnight UTC (saved work is unaffected). A warning
  is logged at `AI_BUDGET_ALERT_RATIO` (default 80%). Spend is computed from `AI_MODEL_PRICES`, which must be real
  prices when deployed.
- **Free plan under concurrency**: the Free check locks the organisation's monthly counter until the request commits,
  so parallel requests can't exceed 30.
- **Downgrade**: workspaces beyond the plan's limit become read-only, newest first (`403 plan_limit_read_only`). Nothing is deleted.

## Error codes

| Status | code |
|---|---|
| 400 | wrong_password, reset_link_invalid, bad_state, state_used, state_expired, scopes_missing, access_denied, not_connectable, use_connect_flow, no_channel, invalid_cursor, invalid_limit, invalid_payload, invalid_key |
| 401 | unauthenticated, invalid_token, invalid_credentials, invalid_refresh_token, invalid_signature |
| 402 | free_limit_reached, workspace_limit_reached, seat_limit_reached |
| 403 | forbidden, product_not_enabled, plan_limit_read_only, approval_required |
| 404 | not_found, user_not_found, file_not_found, link_invalid |
| 409 | transfer_ownership_first, cancel_subscription_first, needs_reauth, revoked, account_changed, integration_planned, no_connection, already_saved, already_set_up, deadline_passed, session_completed, not_approved, wrong_run, no_profile, bad_status, email_in_use, already_member, team_exists, wrong_product, file_not_ready, action_already_decided, action_expired, no_executor, memory_exists |
| 413 | file_too_large, payload_too_large |
| 415 | unsupported_file |
| 422 | terms_required, password_reused, wrong_asset_type, no_such_question, csv_invalid, csv_empty, no_competitors, no_results, currency_required, bad_currency, bad_range, bad_indexes, comment_required, validation_failed, empty_file, file_rejected, credentials_required, not_org_member, agent_not_available, ai_output_invalid, ai_refused, ai_step_limit |
| 429 | account_locked, rate_limited (AI per minute; per-IP sign-in failures, sign-ups, reset requests; integrations), fair_use_review |
| 502 | ai_failed, provider_error, network_error, outcome_unknown, bad_response, bad_request |
| 503 | ai_paused (daily AI budget reached; `Retry-After` = seconds to midnight UTC), email_not_configured, ai_unavailable, webhooks_not_configured, not_configured, outbound_disabled, provider_unavailable |

Integration errors also carry `retryable` (bool).
