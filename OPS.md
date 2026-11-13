# New Age AI ops

Put these at the root of the monorepo, next to `eco-backend/` and `eco-web/`:

```
.github/workflows/   ci.yml, deploy-staging.yml, deploy-production.yml
ops/                 deploy.sh (Render deploy hook + exact image), wait_release.sh (release live + ready)
render/              staging.yaml, production.yaml (Render Blueprints)
runbooks/            deploy-and-rollback, incident-response, disaster-recovery, secrets
LAUNCH_PLAN.md/.pdf  the launch-readiness plan, go-live checklist, risks and phased rollout
```

Backend scripts used by the pipeline and jobs (in `eco-backend/scripts/`): `predeploy`, `migration_safety`, `backup`,
`restore_drill`, `purge_deleted`, `smoke`, `activate_plan`. Web release gate: `eco-web/scripts/check-legal.mjs`.
