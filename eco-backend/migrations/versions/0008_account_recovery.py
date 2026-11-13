"""Account recovery (QA BUG-03): single-use password-reset tokens, a password_changed_at stamp that invalidates
access tokens issued before a reset/change, and an email outbox used ONLY by the dev/test email backend.

Revision ID: 0008_account_recovery
Revises: 0007_integrations
"""
from alembic import context, op

revision = "0008_account_recovery"
down_revision = "0007_integrations"
branch_labels = None
depends_on = None

SCHEMA_SQL = r"""
ALTER TABLE users ADD COLUMN password_changed_at timestamptz;

-- Only sha256(token) is stored. 30-minute lifetime, single use.
CREATE TABLE password_reset_tokens (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  text NOT NULL UNIQUE CHECK (length(token_hash) = 64),
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    used_at     timestamptz
);
CREATE INDEX password_reset_tokens_user_idx ON password_reset_tokens (user_id, created_at DESC);

-- Messages captured by the dev/test email backend. Nothing here is ever sent. Production needs a real provider.
CREATE TABLE email_outbox (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    to_email    citext NOT NULL,
    subject     text NOT NULL CHECK (length(subject) <= 200),
    body        text NOT NULL CHECK (length(body) <= 20000),
    purpose     text NOT NULL CHECK (purpose ~ '^[a-z_]{2,40}$'),
    status      text NOT NULL DEFAULT 'captured_dev' CHECK (status IN ('captured_dev')),
    created_at  timestamptz NOT NULL DEFAULT now()
);
"""


def _app_role() -> str:
    role = context.config.get_main_option("app_role") or "eco_app"
    if not role.replace("_", "").isalnum():
        raise ValueError("invalid app_role")
    return role


def upgrade() -> None:
    role = _app_role()
    op.execute(SCHEMA_SQL)
    for t in ("password_reset_tokens", "email_outbox"):
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {t}_system ON {t} USING (app.is_system()) WITH CHECK (app.is_system())")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO {role}")
        op.execute(f"REVOKE TRUNCATE ON {t} FROM {role}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS email_outbox, password_reset_tokens CASCADE")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_changed_at")
