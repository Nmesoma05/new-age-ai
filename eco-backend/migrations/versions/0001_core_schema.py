"""Core schema: identity, organisations, teams, product access, billing, workspaces,
profiles, documents, conversations, saved outputs, usage, integrations, audit.

Revision ID: 0001_core_schema
Revises:
Create Date: 2026-11-10
"""
from alembic import op

revision = "0001_core_schema"
down_revision = None
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE EXTENSION IF NOT EXISTS citext;

-- ---------------------------------------------------------------- identity
CREATE TABLE users (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email             citext NOT NULL,
    password_hash     text,
    display_name      text NOT NULL CHECK (length(display_name) BETWEEN 1 AND 120),
    country           char(2),
    currency          char(3),
    locale            text NOT NULL DEFAULT 'en',
    timezone          text NOT NULL DEFAULT 'Africa/Lagos',
    email_verified_at timestamptz,
    failed_logins     integer NOT NULL DEFAULT 0 CHECK (failed_logins >= 0),
    locked_until      timestamptz,
    is_active         boolean NOT NULL DEFAULT true,
    external_subject  text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    deleted_at        timestamptz,
    CONSTRAINT users_email_uq UNIQUE (email),
    CONSTRAINT users_external_subject_uq UNIQUE (external_subject)
);

CREATE TABLE refresh_tokens (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    family_id   uuid NOT NULL,
    token_hash  text NOT NULL,
    expires_at  timestamptz NOT NULL,
    revoked_at  timestamptz,
    replaced_by uuid,
    user_agent  text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT refresh_tokens_hash_uq UNIQUE (token_hash)
);
CREATE INDEX refresh_tokens_user_idx ON refresh_tokens (user_id);
CREATE INDEX refresh_tokens_family_idx ON refresh_tokens (family_id);

-- ---------------------------------------------------------------- organisations
CREATE TABLE organisations (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name          text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    kind          text NOT NULL CHECK (kind IN ('personal', 'team')),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    region        text NOT NULL DEFAULT 'default',
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz
);
-- one personal organisation per user
CREATE UNIQUE INDEX organisations_one_personal_uq ON organisations (owner_user_id) WHERE kind = 'personal';

CREATE TABLE org_members (
    org_id     uuid NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role       text NOT NULL CHECK (role IN ('owner', 'admin', 'member', 'billing')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, user_id)
);
CREATE INDEX org_members_user_idx ON org_members (user_id);

CREATE TABLE teams (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     uuid NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    name       text NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT teams_org_name_uq UNIQUE (org_id, name),
    CONSTRAINT teams_id_org_uq UNIQUE (id, org_id)
);

CREATE TABLE team_members (
    team_id    uuid NOT NULL,
    org_id     uuid NOT NULL,
    user_id    uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (team_id, user_id),
    FOREIGN KEY (team_id, org_id) REFERENCES teams(id, org_id) ON DELETE CASCADE,
    FOREIGN KEY (org_id, user_id) REFERENCES org_members(org_id, user_id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------- product access
CREATE TABLE product_access (
    org_id     uuid NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    product    text NOT NULL CHECK (product IN ('creator', 'business', 'freelancer')),
    status     text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'waitlist')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, product)
);

-- ---------------------------------------------------------------- billing
CREATE TABLE plans (
    code               text PRIMARY KEY,
    name               text NOT NULL,
    ai_unlimited       boolean NOT NULL,
    free_monthly_limit integer CHECK (free_monthly_limit IS NULL OR free_monthly_limit >= 0),
    max_workspaces     integer NOT NULL CHECK (max_workspaces > 0),
    max_seats          integer NOT NULL CHECK (max_seats > 0),
    is_paid            boolean NOT NULL,
    CHECK ((ai_unlimited AND free_monthly_limit IS NULL) OR (NOT ai_unlimited AND free_monthly_limit IS NOT NULL))
);
INSERT INTO plans (code, name, ai_unlimited, free_monthly_limit, max_workspaces, max_seats, is_paid) VALUES
    ('free',    'Free',    false, 30,   1,  1,  false),
    ('starter', 'Starter', true,  NULL, 3,  1,  true),
    ('pro',     'Pro',     true,  NULL, 15, 3,  true),
    ('team',    'Team',    true,  NULL, 50, 10, true);

CREATE TABLE subscriptions (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               uuid NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    plan_code            text NOT NULL REFERENCES plans(code),
    status               text NOT NULL CHECK (status IN ('active', 'past_due', 'cancelled', 'expired')),
    provider             text NOT NULL CHECK (provider IN ('paystack', 'card_international', 'manual')),
    provider_ref         text,
    period_start         timestamptz NOT NULL,
    period_end           timestamptz NOT NULL,
    auto_renew           boolean NOT NULL DEFAULT true,
    grace_until          timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    CHECK (period_end > period_start),
    CONSTRAINT subscriptions_provider_ref_uq UNIQUE (provider, provider_ref)
);
-- at most one live subscription per organisation
CREATE UNIQUE INDEX subscriptions_one_live_uq ON subscriptions (org_id) WHERE status IN ('active', 'past_due', 'cancelled');
CREATE INDEX subscriptions_period_end_idx ON subscriptions (period_end) WHERE status IN ('active', 'past_due', 'cancelled');

CREATE TABLE usage_counters (
    org_id                uuid NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    period_month          date NOT NULL CHECK (date_trunc('month', period_month) = period_month),
    free_generations_used integer NOT NULL DEFAULT 0 CHECK (free_generations_used >= 0),
    PRIMARY KEY (org_id, period_month)
);

CREATE TABLE webhook_events (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider    text NOT NULL,
    event_id    text NOT NULL,
    payload     jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    CONSTRAINT webhook_events_uq UNIQUE (provider, event_id)
);

-- ---------------------------------------------------------------- workspaces
CREATE TABLE workspaces (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     uuid NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    product    text NOT NULL CHECK (product IN ('creator', 'business', 'freelancer')),
    name       text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    CONSTRAINT workspaces_id_org_uq UNIQUE (id, org_id)
);
CREATE INDEX workspaces_org_idx ON workspaces (org_id, created_at) WHERE deleted_at IS NULL;

CREATE TABLE workspace_members (
    workspace_id uuid NOT NULL,
    org_id       uuid NOT NULL,
    user_id      uuid NOT NULL,
    role         text NOT NULL CHECK (role IN ('admin', 'editor', 'viewer', 'client_approver')),
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, user_id),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE,
    FOREIGN KEY (org_id, user_id) REFERENCES org_members(org_id, user_id) ON DELETE CASCADE
);
CREATE INDEX workspace_members_user_idx ON workspace_members (user_id);

CREATE TABLE projects (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    org_id       uuid NOT NULL,
    name         text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    description  text,
    status       text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_by   uuid NOT NULL REFERENCES users(id),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT projects_id_ws_uq UNIQUE (id, workspace_id),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE
);
CREATE INDEX projects_ws_idx ON projects (workspace_id, created_at);

-- ---------------------------------------------------------------- division profiles
CREATE TABLE client_accounts (            -- Creator & Marketing: one client per workspace
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  uuid NOT NULL,
    org_id        uuid NOT NULL,
    client_name   text NOT NULL CHECK (length(client_name) BETWEEN 1 AND 120),
    contact_email citext,
    industry      text,
    platforms     text[] NOT NULL DEFAULT '{}',
    brand_voice   jsonb NOT NULL DEFAULT '{}'::jsonb,
    notes         text,
    version       integer NOT NULL DEFAULT 1,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT client_accounts_ws_uq UNIQUE (workspace_id),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE
);

CREATE TABLE business_profiles (          -- Business Marketing
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid NOT NULL,
    org_id          uuid NOT NULL,
    business_name   text NOT NULL CHECK (length(business_name) BETWEEN 1 AND 120),
    industry        text NOT NULL,
    sub_type        text,
    location        text,
    offers          jsonb NOT NULL DEFAULT '[]'::jsonb,
    customers       text,
    differentiators text,
    competitors     jsonb NOT NULL DEFAULT '[]'::jsonb,
    budget_band     text CHECK (budget_band IS NULL OR budget_band IN ('none', 'low', 'medium', 'high')),
    primary_goal    text CHECK (primary_goal IS NULL OR primary_goal IN ('awareness', 'enquiries', 'sales', 'launch')),
    version         integer NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT business_profiles_ws_uq UNIQUE (workspace_id),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE
);

CREATE TABLE professional_profiles (      -- Freelancer Growth: always in the user's personal org
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    org_id       uuid NOT NULL,
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    headline     text,
    summary      text,
    experiences  jsonb NOT NULL DEFAULT '[]'::jsonb,
    education    jsonb NOT NULL DEFAULT '[]'::jsonb,
    skills       jsonb NOT NULL DEFAULT '[]'::jsonb,
    rates        jsonb NOT NULL DEFAULT '{}'::jsonb,
    targets      jsonb NOT NULL DEFAULT '{}'::jsonb,
    version      integer NOT NULL DEFAULT 1,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT professional_profiles_ws_uq UNIQUE (workspace_id),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------- documents
CREATE TABLE documents (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    org_id       uuid NOT NULL,
    project_id   uuid,
    uploaded_by  uuid NOT NULL REFERENCES users(id),
    filename     text NOT NULL CHECK (length(filename) BETWEEN 1 AND 255),
    content_type text NOT NULL CHECK (content_type IN ('application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/plain', 'image/png', 'image/jpeg')),
    size_bytes   bigint NOT NULL CHECK (size_bytes > 0),
    sha256       char(64) NOT NULL,
    storage_key  text NOT NULL,
    scan_status  text NOT NULL DEFAULT 'pending' CHECK (scan_status IN ('pending', 'clean', 'rejected')),
    created_at   timestamptz NOT NULL DEFAULT now(),
    deleted_at   timestamptz,
    CONSTRAINT documents_storage_key_uq UNIQUE (storage_key),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id, workspace_id) REFERENCES projects(id, workspace_id) ON DELETE SET NULL (project_id)
);
CREATE INDEX documents_ws_idx ON documents (workspace_id, created_at DESC, id DESC) WHERE deleted_at IS NULL;

-- ---------------------------------------------------------------- AI usage records
CREATE TABLE ai_usage_records (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    workspace_id  uuid,
    user_id       uuid NOT NULL REFERENCES users(id),
    agent         text NOT NULL,
    model         text NOT NULL,
    status        text NOT NULL CHECK (status IN ('succeeded', 'failed')),
    tokens_in     integer NOT NULL DEFAULT 0 CHECK (tokens_in >= 0),
    tokens_out    integer NOT NULL DEFAULT 0 CHECK (tokens_out >= 0),
    cost_usd      numeric(12, 6) NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
    counted_free  boolean NOT NULL DEFAULT false,
    latency_ms    integer NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
    error_code    text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE SET NULL (workspace_id)
);
CREATE INDEX ai_usage_org_time_idx ON ai_usage_records (org_id, created_at);
CREATE INDEX ai_usage_user_time_idx ON ai_usage_records (user_id, created_at);

-- ---------------------------------------------------------------- conversations and saved outputs
CREATE TABLE conversations (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    org_id       uuid NOT NULL,
    created_by   uuid NOT NULL REFERENCES users(id),
    title        text NOT NULL DEFAULT 'New conversation' CHECK (length(title) BETWEEN 1 AND 200),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT conversations_id_ws_uq UNIQUE (id, workspace_id),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE
);
CREATE INDEX conversations_ws_idx ON conversations (workspace_id, updated_at DESC, id DESC);

CREATE TABLE assets (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid NOT NULL,
    org_id          uuid NOT NULL,
    project_id      uuid,
    type            text NOT NULL CHECK (type IN ('post', 'thread', 'caption', 'script', 'campaign_plan', 'content_plan',
                        'report', 'cv', 'proposal', 'cover_letter', 'case_study', 'note', 'other')),
    title           text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    status          text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'in_review', 'approved', 'posted', 'archived')),
    current_version integer NOT NULL DEFAULT 1 CHECK (current_version >= 1),
    tags            text[] NOT NULL DEFAULT '{}',
    created_by      uuid NOT NULL REFERENCES users(id),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    deleted_at      timestamptz,
    CONSTRAINT assets_id_ws_uq UNIQUE (id, workspace_id),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id, workspace_id) REFERENCES projects(id, workspace_id) ON DELETE SET NULL (project_id)
);
CREATE INDEX assets_ws_idx ON assets (workspace_id, created_at DESC, id DESC) WHERE deleted_at IS NULL;
CREATE INDEX assets_tags_idx ON assets USING gin (tags);

CREATE TABLE asset_versions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id        uuid NOT NULL,
    workspace_id    uuid NOT NULL,
    org_id          uuid NOT NULL,
    version         integer NOT NULL CHECK (version >= 1),
    body            jsonb NOT NULL,
    body_text       text NOT NULL DEFAULT '',
    source          text NOT NULL CHECK (source IN ('ai', 'human')),
    usage_record_id uuid REFERENCES ai_usage_records(id) ON DELETE SET NULL,
    author_id       uuid NOT NULL REFERENCES users(id),
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT asset_versions_uq UNIQUE (asset_id, version),
    FOREIGN KEY (asset_id, workspace_id) REFERENCES assets(id, workspace_id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE
);

CREATE TABLE messages (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id uuid NOT NULL,
    workspace_id    uuid NOT NULL,
    org_id          uuid NOT NULL,
    role            text NOT NULL CHECK (role IN ('user', 'assistant')),
    content         text NOT NULL CHECK (length(content) BETWEEN 1 AND 32000),
    author_id       uuid REFERENCES users(id),
    asset_id        uuid,
    usage_record_id uuid REFERENCES ai_usage_records(id) ON DELETE SET NULL,
    created_at      timestamptz NOT NULL DEFAULT clock_timestamp(),  -- distinct times within one transaction
    FOREIGN KEY (conversation_id, workspace_id) REFERENCES conversations(id, workspace_id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id, workspace_id) REFERENCES assets(id, workspace_id) ON DELETE SET NULL (asset_id),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE
);
CREATE INDEX messages_conv_idx ON messages (conversation_id, created_at, id);

-- ---------------------------------------------------------------- integrations
CREATE TABLE integrations (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                uuid NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    workspace_id          uuid,
    provider              text NOT NULL CHECK (provider ~ '^[a-z0-9_]{2,40}$'),
    status                text NOT NULL DEFAULT 'connected' CHECK (status IN ('connected', 'revoked', 'error')),
    account_label         text,
    scopes                text[] NOT NULL DEFAULT '{}',
    encrypted_credentials bytea NOT NULL,
    created_by            uuid NOT NULL REFERENCES users(id),
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE
);
CREATE INDEX integrations_org_idx ON integrations (org_id);

-- ---------------------------------------------------------------- audit log (append only)
CREATE TABLE audit_events (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id        uuid REFERENCES organisations(id) ON DELETE SET NULL,
    workspace_id  uuid,
    actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    action        text NOT NULL CHECK (action ~ '^[a-z_]+\.[a-z_]+$'),
    target_type   text,
    target_id     text,
    metadata      jsonb NOT NULL DEFAULT '{}'::jsonb,
    ip            inet,
    user_agent    text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_org_idx ON audit_events (org_id, id DESC);

CREATE FUNCTION audit_events_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        -- the only permitted update is the FK cascade nulling a deleted org/user reference
        IF NEW.action = OLD.action AND NEW.metadata = OLD.metadata AND NEW.created_at = OLD.created_at
           AND (NEW.org_id IS NULL OR NEW.org_id = OLD.org_id)
           AND (NEW.actor_user_id IS NULL OR NEW.actor_user_id = OLD.actor_user_id) THEN
            RETURN NEW;
        END IF;
    END IF;
    RAISE EXCEPTION 'audit_events is append-only';
END $$;
CREATE TRIGGER audit_events_no_update BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();

-- ---------------------------------------------------------------- updated_at maintenance
CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END $$;
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['users','organisations','subscriptions','workspaces','projects','client_accounts',
        'business_profiles','professional_profiles','conversations','assets','integrations'] LOOP
        EXECUTE format('CREATE TRIGGER %I_updated_at BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION set_updated_at()', t, t);
    END LOOP;
END $$;
"""

DOWNGRADE_SQL = r"""
DROP TABLE IF EXISTS audit_events, integrations, messages, asset_versions, assets, conversations, ai_usage_records,
    documents, professional_profiles, business_profiles, client_accounts, projects, workspace_members, workspaces,
    webhook_events, usage_counters, subscriptions, plans, product_access, team_members, teams, org_members,
    organisations, refresh_tokens, users CASCADE;
DROP FUNCTION IF EXISTS audit_events_immutable();
DROP FUNCTION IF EXISTS set_updated_at();
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
