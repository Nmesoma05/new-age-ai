"""Launch readiness: terms acceptance on users, read access to the migration version for /ready, and shared
per-IP attempt counters (auth_attempts) so limits hold across workers and instances.

Revision ID: 0009_launch
Revises: 0008_account_recovery
"""
from alembic import context, op

revision = "0009_launch"
down_revision = "0008_account_recovery"
branch_labels = None
depends_on = None


def _app_role() -> str:
    role = context.config.get_main_option("app_role") or "eco_app"
    if not role.replace("_", "").isalnum():
        raise ValueError("invalid app_role")
    return role


def upgrade() -> None:
    # Additive only: safe to run while the previous release is still serving (expand/contract).
    op.execute("ALTER TABLE users ADD COLUMN terms_version text, ADD COLUMN terms_accepted_at timestamptz")
    op.execute(f"GRANT SELECT ON alembic_version TO {_app_role()}")
    # Per-IP attempt counters for sign-in/sign-up/reset, shared by every worker and instance (no Redis needed).
    op.execute("""CREATE TABLE auth_attempts (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        bucket text NOT NULL, ip inet NOT NULL, at timestamptz NOT NULL DEFAULT now())""")
    op.execute("CREATE INDEX auth_attempts_lookup ON auth_attempts (bucket, ip, at)")
    op.execute("ALTER TABLE auth_attempts ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY auth_attempts_system ON auth_attempts USING (app.is_system()) WITH CHECK (app.is_system())")
    op.execute(f"GRANT SELECT, INSERT, DELETE ON auth_attempts TO {_app_role()}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS auth_attempts")
    op.execute(f"REVOKE SELECT ON alembic_version FROM {_app_role()}")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS terms_accepted_at, DROP COLUMN IF EXISTS terms_version")
