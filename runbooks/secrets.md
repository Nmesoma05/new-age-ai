# Secrets

| Secret | Where it lives | Rotation |
|---|---|---|
| JWT_SECRET (≥32 chars) | Host env group, per environment | Yearly or on suspicion (signs everyone out) |
| CREDENTIALS_ENCRYPTION_KEY | Host env group | Yearly: prepend new key, deploy, remove old after re-encryption |
| DATABASE_URL (eco_app) / MIGRATIONS_DATABASE_URL (eco_owner) | Host env group | Yearly; owner URL only in API/jobs, never the web service |
| OPENAI_API_KEY / ANTHROPIC_API_KEY | Host env group; separate project per environment | 90 days |
| PAYSTACK_SECRET_KEY | Host env group: `sk_test_` in staging, `sk_live_` in production (the app refuses the wrong one) | On staff change |
| SMTP_PASSWORD | Host env group | 90 days |
| GOOGLE_OAUTH_CLIENT_SECRET | Host env group | Yearly |
| SENTRY_DSN | Host env group | n/a (not secret enough to rotate routinely) |
| S3 / backup bucket keys | Host env group; backup writer can't delete (object lock) | 90 days |
| RENDER_DEPLOY_HOOK_*, SMOKE_EMAIL/PASSWORD | GitHub environment secrets (staging / production separately) | On staff change |

Rules: never in git (CI fails on `.env` files; .dockerignore excludes them), never in the web bundle (the browser test checks), never logged (logs redact; tested). Only two people have production access; access is reviewed monthly. Use 2FA on GitHub, the host, Paystack, the AI provider and the domain registrar.
