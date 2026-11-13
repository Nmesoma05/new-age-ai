"""Creator & Marketing division: richer client profiles, campaigns, content calendar, review workflow,
client review links and performance data.

Performance data is entered by people (manually or by CSV upload) until a platform analytics integration
exists; every metrics row records its `source` so reports can say where numbers came from.

Revision ID: 0004_creator
Revises: 0003_ai_engine
"""
from alembic import context, op

revision = "0004_creator"
down_revision = "0003_ai_engine"
branch_labels = None
depends_on = None

PLATFORMS = "'instagram','x','linkedin','tiktok','facebook','youtube','threads','whatsapp','pinterest','other'"
NEW_TABLES = ["campaigns", "calendar_items", "asset_comments", "review_links", "post_metrics", "follower_snapshots"]

SCHEMA_SQL = rf"""
-- ------------------------------------------------------------ client profile (one client per creator workspace)
ALTER TABLE client_accounts
    ADD COLUMN website        text CHECK (website IS NULL OR website ~ '^https?://'),
    ADD COLUMN business_info  jsonb NOT NULL DEFAULT '{{}}'::jsonb,   -- description, offers, location
    ADD COLUMN audience       jsonb NOT NULL DEFAULT '{{}}'::jsonb,   -- summary, personas[], locations[]
    ADD COLUMN goals          jsonb NOT NULL DEFAULT '[]'::jsonb,     -- [{{goal, metric, due}}]
    ADD COLUMN competitors    jsonb NOT NULL DEFAULT '[]'::jsonb,     -- [{{name, handle, platform, notes}}]
    ADD COLUMN content_pillars jsonb NOT NULL DEFAULT '[]'::jsonb;    -- [{{name, purpose, example_topics[]}}]

ALTER TABLE assets DROP CONSTRAINT assets_type_check;
ALTER TABLE assets ADD CONSTRAINT assets_type_check CHECK (type IN ('post', 'thread', 'caption', 'script',
    'campaign_plan', 'content_plan', 'report', 'cv', 'proposal', 'cover_letter', 'case_study', 'note', 'other',
    'brand_voice', 'research', 'calendar_plan'));

-- ------------------------------------------------------------ campaigns
CREATE TABLE campaigns (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  uuid NOT NULL,
    org_id        uuid NOT NULL,
    name          text NOT NULL CHECK (length(name) BETWEEN 1 AND 160),
    objective     text NOT NULL DEFAULT '' CHECK (length(objective) <= 1000),
    status        text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'completed', 'archived')),
    start_date    date,
    end_date      date,
    channels      text[] NOT NULL DEFAULT '{{}}',
    budget_note   text NOT NULL DEFAULT '' CHECK (length(budget_note) <= 1000),
    plan          jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    source_run_id uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
    created_by    uuid NOT NULL REFERENCES users(id),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date),
    CONSTRAINT campaigns_id_ws_uq UNIQUE (id, workspace_id),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE
);
CREATE INDEX campaigns_ws_idx ON campaigns (workspace_id, created_at DESC, id DESC);

-- ------------------------------------------------------------ content calendar
-- 'published_manually' means a person posted it themselves and recorded it; nothing here publishes.
CREATE TABLE calendar_items (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  uuid NOT NULL,
    org_id        uuid NOT NULL,
    campaign_id   uuid,
    asset_id      uuid,
    title         text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    platform      text NOT NULL CHECK (platform IN ({PLATFORMS})),
    format        text NOT NULL DEFAULT 'post' CHECK (length(format) BETWEEN 1 AND 40),
    pillar        text CHECK (pillar IS NULL OR length(pillar) <= 80),
    notes         text NOT NULL DEFAULT '' CHECK (length(notes) <= 4000),
    scheduled_for timestamptz NOT NULL,
    status        text NOT NULL DEFAULT 'planned'
                  CHECK (status IN ('planned', 'drafted', 'ready', 'published_manually', 'skipped')),
    published_url text CHECK (published_url IS NULL OR published_url ~ '^https?://'),
    published_at  timestamptz,
    source        text NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'ai_plan')),
    source_run_id uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
    created_by    uuid NOT NULL REFERENCES users(id),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CHECK ((status = 'published_manually') = (published_at IS NOT NULL)),
    CONSTRAINT calendar_items_id_ws_uq UNIQUE (id, workspace_id),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE,
    FOREIGN KEY (campaign_id, workspace_id) REFERENCES campaigns(id, workspace_id) ON DELETE SET NULL (campaign_id),
    FOREIGN KEY (asset_id, workspace_id) REFERENCES assets(id, workspace_id) ON DELETE SET NULL (asset_id)
);
CREATE INDEX calendar_items_ws_time_idx ON calendar_items (workspace_id, scheduled_for);
CREATE INDEX calendar_items_campaign_idx ON calendar_items (campaign_id) WHERE campaign_id IS NOT NULL;

-- ------------------------------------------------------------ review workflow
CREATE TABLE asset_comments (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id   uuid NOT NULL,
    org_id         uuid NOT NULL,
    asset_id       uuid NOT NULL,
    asset_version  integer NOT NULL CHECK (asset_version >= 1),
    kind           text NOT NULL CHECK (kind IN ('comment', 'submitted', 'changes_requested', 'approved')),
    body           text NOT NULL DEFAULT '' CHECK (length(body) <= 4000),
    via            text NOT NULL CHECK (via IN ('team', 'client_link')),
    author_user_id uuid REFERENCES users(id),
    author_name    text CHECK (author_name IS NULL OR length(author_name) BETWEEN 1 AND 120),
    review_link_id uuid,
    created_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((via = 'team') = (author_user_id IS NOT NULL)),
    CHECK (via = 'team' OR (author_name IS NOT NULL AND review_link_id IS NOT NULL)),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id, workspace_id) REFERENCES assets(id, workspace_id) ON DELETE CASCADE
);
CREATE INDEX asset_comments_asset_idx ON asset_comments (asset_id, created_at);

-- A client review link shows chosen assets to someone without an account. Only the SHA-256 of the token is stored.
CREATE TABLE review_links (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id   uuid NOT NULL,
    org_id         uuid NOT NULL,
    token_hash     text NOT NULL UNIQUE,
    label          text NOT NULL CHECK (length(label) BETWEEN 1 AND 120),
    asset_ids      uuid[] NOT NULL CHECK (cardinality(asset_ids) BETWEEN 1 AND 50),
    allow_approve  boolean NOT NULL DEFAULT true,
    created_by     uuid NOT NULL REFERENCES users(id),
    expires_at     timestamptz NOT NULL,
    revoked_at     timestamptz,
    last_viewed_at timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE
);
CREATE INDEX review_links_ws_idx ON review_links (workspace_id, created_at DESC, id DESC);
ALTER TABLE asset_comments ADD FOREIGN KEY (review_link_id) REFERENCES review_links(id) ON DELETE SET NULL;

-- ------------------------------------------------------------ performance data
CREATE TABLE post_metrics (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id     uuid NOT NULL,
    org_id           uuid NOT NULL,
    calendar_item_id uuid,
    asset_id         uuid,
    platform         text NOT NULL CHECK (platform IN ({PLATFORMS})),
    post_url         text CHECK (post_url IS NULL OR post_url ~ '^https?://'),
    post_label       text NOT NULL CHECK (length(post_label) BETWEEN 1 AND 200),
    published_on     date NOT NULL,
    captured_on      date NOT NULL DEFAULT current_date,
    impressions      bigint CHECK (impressions >= 0),
    reach            bigint CHECK (reach >= 0),
    likes            bigint CHECK (likes >= 0),
    comments         bigint CHECK (comments >= 0),
    shares           bigint CHECK (shares >= 0),
    saves            bigint CHECK (saves >= 0),
    clicks           bigint CHECK (clicks >= 0),
    video_views      bigint CHECK (video_views >= 0),
    source           text NOT NULL CHECK (source IN ('manual', 'csv_import', 'integration')),
    notes            text NOT NULL DEFAULT '' CHECK (length(notes) <= 1000),
    created_by       uuid NOT NULL REFERENCES users(id),
    created_at       timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE,
    FOREIGN KEY (calendar_item_id, workspace_id) REFERENCES calendar_items(id, workspace_id) ON DELETE SET NULL (calendar_item_id),
    FOREIGN KEY (asset_id, workspace_id) REFERENCES assets(id, workspace_id) ON DELETE SET NULL (asset_id)
);
CREATE INDEX post_metrics_ws_date_idx ON post_metrics (workspace_id, published_on);

CREATE TABLE follower_snapshots (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    org_id       uuid NOT NULL,
    platform     text NOT NULL CHECK (platform IN ({PLATFORMS})),
    captured_on  date NOT NULL,
    followers    bigint NOT NULL CHECK (followers >= 0),
    source       text NOT NULL CHECK (source IN ('manual', 'csv_import', 'integration')),
    created_by   uuid NOT NULL REFERENCES users(id),
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT follower_snapshots_uq UNIQUE (workspace_id, platform, captured_on),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE
);

CREATE TRIGGER campaigns_updated BEFORE UPDATE ON campaigns FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER calendar_items_updated BEFORE UPDATE ON calendar_items FOR EACH ROW EXECUTE FUNCTION set_updated_at();
"""

POLICIES_SQL = """
CREATE POLICY campaigns_select ON campaigns FOR SELECT USING (app.can_read_ws(workspace_id));
CREATE POLICY campaigns_write ON campaigns FOR ALL USING (app.can_write_ws(workspace_id)) WITH CHECK (app.can_write_ws(workspace_id));
CREATE POLICY calendar_select ON calendar_items FOR SELECT USING (app.can_read_ws(workspace_id));
CREATE POLICY calendar_write ON calendar_items FOR ALL USING (app.can_write_ws(workspace_id)) WITH CHECK (app.can_write_ws(workspace_id));
CREATE POLICY post_metrics_select ON post_metrics FOR SELECT USING (app.can_read_ws(workspace_id));
CREATE POLICY post_metrics_write ON post_metrics FOR ALL USING (app.can_write_ws(workspace_id)) WITH CHECK (app.can_write_ws(workspace_id));
CREATE POLICY followers_select ON follower_snapshots FOR SELECT USING (app.can_read_ws(workspace_id));
CREATE POLICY followers_write ON follower_snapshots FOR ALL USING (app.can_write_ws(workspace_id)) WITH CHECK (app.can_write_ws(workspace_id));

-- comments are append-only; team members write as themselves, client-link comments only in system context
CREATE POLICY asset_comments_select ON asset_comments FOR SELECT USING (app.can_read_ws(workspace_id));
CREATE POLICY asset_comments_insert ON asset_comments FOR INSERT WITH CHECK (
    app.is_system() OR (app.can_read_ws(workspace_id) AND via = 'team' AND author_user_id = app.uid()));

-- review links: workspace writers manage them; the public review endpoint reads them in system context
CREATE POLICY review_links_select ON review_links FOR SELECT USING (app.can_read_ws(workspace_id));
CREATE POLICY review_links_write ON review_links FOR ALL USING (app.can_write_ws(workspace_id)) WITH CHECK (app.can_write_ws(workspace_id));
"""


def _app_role() -> str:
    role = context.config.get_main_option("app_role") or "eco_app"
    if not role.replace("_", "").isalnum():
        raise ValueError("invalid app_role")
    return role


def upgrade() -> None:
    role = _app_role()
    op.execute(SCHEMA_SQL)
    for t in NEW_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
    op.execute(POLICIES_SQL)
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON campaigns, calendar_items, review_links, post_metrics, "
               f"follower_snapshots TO {role}")
    op.execute(f"GRANT SELECT, INSERT ON asset_comments TO {role}")
    op.execute(f"REVOKE TRUNCATE ON {', '.join(NEW_TABLES)} FROM {role}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS follower_snapshots, post_metrics, asset_comments, review_links, calendar_items, "
               "campaigns CASCADE")
    op.execute("DELETE FROM asset_versions WHERE asset_id IN (SELECT id FROM assets WHERE type IN "
               "('brand_voice', 'research', 'calendar_plan'))")
    op.execute("DELETE FROM assets WHERE type IN ('brand_voice', 'research', 'calendar_plan')")
    op.execute("ALTER TABLE assets DROP CONSTRAINT assets_type_check")
    op.execute("ALTER TABLE assets ADD CONSTRAINT assets_type_check CHECK (type IN ('post', 'thread', 'caption', "
               "'script', 'campaign_plan', 'content_plan', 'report', 'cv', 'proposal', 'cover_letter', 'case_study', "
               "'note', 'other'))")
    op.execute("ALTER TABLE client_accounts DROP COLUMN website, DROP COLUMN business_info, DROP COLUMN audience, "
               "DROP COLUMN goals, DROP COLUMN competitors, DROP COLUMN content_pillars")
