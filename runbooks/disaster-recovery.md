# Disaster recovery

Targets for launch: **RPO** (data you can lose) ≤ 5 minutes with point-in-time recovery, ≤ 24 h from the logical backup; **RTO** (time to recover) ≤ 4 hours.

## Layers
1. Host point-in-time recovery (Render Pro: 7 days) for "restore to 10:41 yesterday".
2. Daily logical backup (`scripts.backup`, 02:15 UTC) to a separate, private, versioned bucket in another account, kept 35 days. Also taken automatically before every migration.
3. File storage: bucket versioning on, so deleted or overwritten files can be recovered for 30 days.
4. Monthly restore drill (`scripts.restore_drill`), into a separate server. A failed drill is a SEV2.

## Restore the database
1. Declare a SEV1; put the app in maintenance mode.
2. Choose: point-in-time (host dashboard → database → Recovery → new instance at timestamp), or the latest logical backup.
3. Logical backup: create a new Postgres 16 instance; run `scripts/create_roles.sql`; `pg_restore --no-comments --dbname=<new> <dump>` (as in the drill); check counts against the manifest.
4. Point the services at the new database (DATABASE_URL, MIGRATIONS_DATABASE_URL), deploy, check `/ready`, run the smoke test.
5. Tell users what window of data, if any, was lost.

Rehearsed 13 Nov 2026: backup to S3-compatible storage and restore drill passed (47 tables, schema checked, RLS on, grants intact) in about 1 second for a small database. Repeat on staging with production-like volume before launch.

## Lost secrets
JWT secret: rotate (everyone signs in again). Encryption key: add the new key first (`NEW,OLD`), deploy, let rows re-encrypt, then remove the old. Never delete the old key before that, or connected accounts can't be decrypted.
