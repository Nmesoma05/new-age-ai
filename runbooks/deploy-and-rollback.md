# Deploy and roll back

## Normal release
1. Merge to `main`. CI runs: lint, dependency audit, migration gate, 332 backend tests, 5 browser suites, cross-tenant sweep, image build + vulnerability scan. Any failure stops here.
2. "Deploy staging" runs automatically: deploys that commit's images, the host runs `scripts.predeploy` (gate, backup, migrate), then the full smoke test with a throwaway account and the real AI model.
3. Check staging yourself for anything user-visible (5 minutes).
4. Actions → "Deploy production" → enter the commit SHA and a one-line reason. A second person approves. Gates: staging passed for that SHA, legal pages approved, no deploy freeze.
5. The pipeline deploys, waits for `/health` to report the SHA and `/ready` to pass, runs the production smoke test, and **rolls back automatically** if it fails.
6. Watch error tracking and the dashboard for 15 minutes.

Deploy windows: Tuesday–Thursday, 10:00–15:00 Lagos time. No Friday or pre-holiday deploys. Hotfixes follow the same path; only the waiting shrinks.

## Manual rollback
When: error rate up, a core flow broken, or anything you can't explain within 15 minutes of a release.
1. Actions → "Deploy production" with the **previous** SHA (shown in the last successful run's summary), reason "rollback: …". Or in Render: the service → Deploys → previous deploy → Redeploy.
2. Restore the matching environment variables if the release changed any (the env-var change log in the release notes says which).
3. Schema stays as it is: migrations are additive (the gate enforces it), so the previous code runs on the newer schema. Rehearsed on 13 Nov: the previous release signed up, created workspaces and signed in on the new schema.
4. Confirm with `python -m scripts.smoke --mode production …`, then post in #incidents.

## Destructive migration (rare, planned)
Ship in two releases: first stop using the column/table (and deploy), then a later release removes it with `ALLOW_DESTRUCTIVE_MIGRATION=<revision>` set for that deploy only, after a manual backup.
