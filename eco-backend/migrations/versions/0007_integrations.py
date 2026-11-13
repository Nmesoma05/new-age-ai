"""Integration framework: per-workspace connections with encrypted tokens, single-use OAuth state, an outbound
call log (no secrets, no bodies), and a cache for public provider data shared by everyone (exchange rates, public
job feeds) so we respect providers' fetch limits app-wide.

Revision ID: 0007_integrations
Revises: 0006_freelancer
"""
from alembic import context, op

revision = "0007_integrations"
down_revision = "0006_freelancer"
branch_labels = None
depends_on = None

SCHEMA_SQL = r"""
ALTER TABLE integrations DROP CONSTRAINT integrations_status_check;
ALTER TABLE integrations ADD CONSTRAINT integrations_status_check
    CHECK (status IN ('connected', 'revoked', 'error', 'needs_reauth'));
ALTER TABLE integrations
    ADD COLUMN auth_type            text NOT NULL DEFAULT 'oauth2' CHECK (auth_type IN ('oauth2', 'api_key', 'none')),
    ADD COLUMN external_account_id  text CHECK (external_account_id IS NULL OR length(external_account_id) <= 200),
    ADD COLUMN token_expires_at     timestamptz,
    ADD COLUMN key_version          integer NOT NULL DEFAULT 1,
    ADD COLUMN last_refreshed_at    timestamptz,
    ADD COLUMN last_used_at         timestamptz,
    ADD COLUMN last_sync_at         timestamptz,
    ADD COLUMN last_error           text CHECK (last_error IS NULL OR length(last_error) <= 300),
    ADD COLUMN last_error_at        timestamptz,
    ADD COLUMN consecutive_failures integer NOT NULL DEFAULT 0;
CREATE UNIQUE INDEX integrations_live_account_uq ON integrations (workspace_id, provider, external_account_id)
    WHERE status <> 'revoked';

-- One row per authorisation attempt. Only a hash of `state` is stored; the PKCE verifier is encrypted.
CREATE TABLE oauth_states (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    state_hash       text NOT NULL UNIQUE CHECK (length(state_hash) = 64),
    provider         text NOT NULL CHECK (provider ~ '^[a-z0-9_]{2,40}$'),
    user_id          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id           uuid NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    workspace_id     uuid NOT NULL,
    encrypted_verifier bytea NOT NULL,
    scopes           text[] NOT NULL,
    return_to        text NOT NULL CHECK (return_to ~ '^/[A-Za-z0-9/_\-]*$'),
    created_at       timestamptz NOT NULL DEFAULT now(),
    expires_at       timestamptz NOT NULL,
    used_at          timestamptz,
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE
);

-- Outbound calls: what, when, how it went. Never tokens, query strings or bodies.
CREATE TABLE integration_calls (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    integration_id uuid REFERENCES integrations(id) ON DELETE SET NULL,
    org_id         uuid,
    workspace_id   uuid,
    provider       text NOT NULL,
    operation      text NOT NULL CHECK (length(operation) <= 80),
    method         text NOT NULL,
    host           text NOT NULL,
    path           text NOT NULL CHECK (length(path) <= 300),
    status_code    integer,
    outcome        text NOT NULL CHECK (outcome IN ('ok', 'retried', 'client_error', 'auth_error', 'rate_limited',
                                                     'server_error', 'network_error', 'circuit_open', 'blocked')),
    attempt        integer NOT NULL DEFAULT 1,
    latency_ms     integer,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX integration_calls_ws_idx ON integration_calls (workspace_id, created_at DESC);
CREATE INDEX integration_calls_provider_idx ON integration_calls (provider, created_at DESC);

-- Public, non-tenant provider data (e.g. today's exchange rates, a public job feed snapshot).
CREATE TABLE external_cache (
    cache_key   text PRIMARY KEY CHECK (length(cache_key) <= 200),
    provider    text NOT NULL,
    payload     jsonb NOT NULL,
    fetched_at  timestamptz NOT NULL,
    expires_at  timestamptz NOT NULL
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
    # OAuth state: only the server (system context) reads or writes it.
    op.execute("ALTER TABLE oauth_states ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY oauth_states_system ON oauth_states USING (app.is_system()) WITH CHECK (app.is_system())")
    # Call log: org admins read their org's rows; the server writes.
    op.execute("ALTER TABLE integration_calls ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY integration_calls_select ON integration_calls FOR SELECT "
               "USING (app.is_system() OR (org_id IS NOT NULL AND app.is_org_admin(org_id)))")
    op.execute("CREATE POLICY integration_calls_insert ON integration_calls FOR INSERT WITH CHECK (app.is_system())")
    # Public cache: anyone signed in may read; only the server writes.
    op.execute("ALTER TABLE external_cache ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY external_cache_select ON external_cache FOR SELECT USING (true)")
    op.execute("CREATE POLICY external_cache_write ON external_cache FOR ALL USING (app.is_system()) "
               "WITH CHECK (app.is_system())")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON oauth_states, external_cache TO {role}")
    op.execute(f"GRANT SELECT, INSERT ON integration_calls TO {role}")
    op.execute(f"REVOKE TRUNCATE ON oauth_states, external_cache, integration_calls FROM {role}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS external_cache, integration_calls, oauth_states CASCADE")
    op.execute("DROP INDEX IF EXISTS integrations_live_account_uq")
    op.execute("ALTER TABLE integrations DROP COLUMN auth_type, DROP COLUMN external_account_id, "
               "DROP COLUMN token_expires_at, DROP COLUMN key_version, DROP COLUMN last_refreshed_at, "
               "DROP COLUMN last_used_at, DROP COLUMN last_sync_at, DROP COLUMN last_error, DROP COLUMN last_error_at, "
               "DROP COLUMN consecutive_failures")
    op.execute("UPDATE integrations SET status = 'error' WHERE status = 'needs_reauth'")
    op.execute("ALTER TABLE integrations DROP CONSTRAINT integrations_status_check")
    op.execute("ALTER TABLE integrations ADD CONSTRAINT integrations_status_check "
               "CHECK (status IN ('connected', 'revoked', 'error'))")
