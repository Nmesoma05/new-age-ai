"""Business Marketing division: richer business profile + editable Marketing Intelligence Profile, and recorded
marketing results (spend, leads, customers, revenue by channel and period).

Results are entered by people (manually or CSV) until ad-platform / CRM / analytics integrations exist; every row
records its `source`.

Revision ID: 0005_business
Revises: 0004_creator
"""
from alembic import context, op

revision = "0005_business"
down_revision = "0004_creator"
branch_labels = None
depends_on = None

CHANNELS = ("'instagram','facebook','tiktok','x','linkedin','youtube','whatsapp','google_search_ads','meta_ads',"
            "'email','sms','website_seo','google_business_profile','marketplaces','referrals','events','partnerships',"
            "'print_outdoor','radio_tv','sales_outreach','other'")

SCHEMA_SQL = rf"""
ALTER TABLE business_profiles
    ADD COLUMN category       text NOT NULL DEFAULT 'other',
    ADD COLUMN stage          text NOT NULL DEFAULT 'growing'
                              CHECK (stage IN ('idea', 'new', 'growing', 'established')),
    ADD COLUMN business_model text NOT NULL DEFAULT 'b2c' CHECK (business_model IN ('b2c', 'b2b', 'both')),
    ADD COLUMN target_markets jsonb NOT NULL DEFAULT '[]'::jsonb,   -- ["Lagos", "Abuja", "UK diaspora"]
    ADD COLUMN channels       jsonb NOT NULL DEFAULT '[]'::jsonb,   -- [{{channel, status: using|tried|considering, notes}}]
    ADD COLUMN goals          jsonb NOT NULL DEFAULT '[]'::jsonb,   -- [{{goal, metric, target, due}}]
    ADD COLUMN budget         jsonb NOT NULL DEFAULT '{{}}'::jsonb, -- {{monthly_amount, currency, notes}}
    ADD COLUMN brand          jsonb NOT NULL DEFAULT '{{}}'::jsonb, -- positioning & messaging (applied from AI or typed)
    ADD COLUMN intelligence   jsonb NOT NULL DEFAULT '{{}}'::jsonb, -- the editable Marketing Intelligence Profile
    ADD COLUMN intelligence_updated_at timestamptz,
    ADD COLUMN website        text CHECK (website IS NULL OR website ~ '^https?://');

ALTER TABLE assets DROP CONSTRAINT assets_type_check;
ALTER TABLE assets ADD CONSTRAINT assets_type_check CHECK (type IN ('post', 'thread', 'caption', 'script',
    'campaign_plan', 'content_plan', 'report', 'cv', 'proposal', 'cover_letter', 'case_study', 'note', 'other',
    'brand_voice', 'research', 'calendar_plan', 'marketing_plan', 'positioning', 'competitor_analysis', 'ad_plan',
    'growth_plan', 'intelligence_profile'));

CREATE TABLE marketing_results (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    org_id       uuid NOT NULL,
    campaign_id  uuid,
    channel      text NOT NULL CHECK (channel IN ({CHANNELS})),
    period_start date NOT NULL,
    period_end   date NOT NULL,
    currency     text NOT NULL CHECK (currency ~ '^[A-Z]{{3}}$'),
    spend        numeric(14,2) CHECK (spend >= 0),
    impressions  bigint CHECK (impressions >= 0),
    clicks       bigint CHECK (clicks >= 0),
    leads        bigint CHECK (leads >= 0),
    customers    bigint CHECK (customers >= 0),
    revenue      numeric(14,2) CHECK (revenue >= 0),
    source       text NOT NULL CHECK (source IN ('manual', 'csv_import', 'integration')),
    notes        text NOT NULL DEFAULT '' CHECK (length(notes) <= 1000),
    created_by   uuid NOT NULL REFERENCES users(id),
    created_at   timestamptz NOT NULL DEFAULT now(),
    CHECK (period_end >= period_start),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE,
    FOREIGN KEY (campaign_id, workspace_id) REFERENCES campaigns(id, workspace_id) ON DELETE SET NULL (campaign_id)
);
CREATE INDEX marketing_results_ws_idx ON marketing_results (workspace_id, period_start);
"""

POLICIES_SQL = """
CREATE POLICY marketing_results_select ON marketing_results FOR SELECT USING (app.can_read_ws(workspace_id));
CREATE POLICY marketing_results_write ON marketing_results FOR ALL
    USING (app.can_write_ws(workspace_id)) WITH CHECK (app.can_write_ws(workspace_id));
"""


def _app_role() -> str:
    role = context.config.get_main_option("app_role") or "eco_app"
    if not role.replace("_", "").isalnum():
        raise ValueError("invalid app_role")
    return role


def upgrade() -> None:
    role = _app_role()
    op.execute(SCHEMA_SQL)
    op.execute("ALTER TABLE marketing_results ENABLE ROW LEVEL SECURITY")
    op.execute(POLICIES_SQL)
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON marketing_results TO {role}")
    op.execute(f"REVOKE TRUNCATE ON marketing_results FROM {role}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS marketing_results CASCADE")
    new = "('marketing_plan', 'positioning', 'competitor_analysis', 'ad_plan', 'growth_plan', 'intelligence_profile')"
    op.execute(f"DELETE FROM asset_versions WHERE asset_id IN (SELECT id FROM assets WHERE type IN {new})")
    op.execute(f"DELETE FROM assets WHERE type IN {new}")
    op.execute("ALTER TABLE assets DROP CONSTRAINT assets_type_check")
    op.execute("ALTER TABLE assets ADD CONSTRAINT assets_type_check CHECK (type IN ('post', 'thread', 'caption', "
               "'script', 'campaign_plan', 'content_plan', 'report', 'cv', 'proposal', 'cover_letter', 'case_study', "
               "'note', 'other', 'brand_voice', 'research', 'calendar_plan'))")
    op.execute("ALTER TABLE business_profiles DROP COLUMN category, DROP COLUMN stage, DROP COLUMN business_model, "
               "DROP COLUMN target_markets, DROP COLUMN channels, DROP COLUMN goals, DROP COLUMN budget, "
               "DROP COLUMN brand, DROP COLUMN intelligence, DROP COLUMN intelligence_updated_at, DROP COLUMN website")
