"""Freelancer Growth division: a reusable professional profile, saved opportunities (external, unverified until the
user checks the source), an application tracker and mock-interview sessions.

Opportunities are entered or pasted by the user; there is no job-board feed. Each one records where it came from,
when (and whether) the user verified it at the source, and expires automatically after its deadline.

Revision ID: 0006_freelancer
Revises: 0005_business
"""
from alembic import context, op

revision = "0006_freelancer"
down_revision = "0005_business"
branch_labels = None
depends_on = None

NEW_ASSET_TYPES = ("'skills_assessment', 'interview_prep', 'portfolio', 'service_package', 'outreach_plan', "
                   "'learning_plan', 'opportunity_analysis', 'brand_content'")
OLD_ASSET_TYPES = ("'post', 'thread', 'caption', 'script', 'campaign_plan', 'content_plan', 'report', 'cv', 'proposal', "
                   "'cover_letter', 'case_study', 'note', 'other', 'brand_voice', 'research', 'calendar_plan', "
                   "'marketing_plan', 'positioning', 'competitor_analysis', 'ad_plan', 'growth_plan', "
                   "'intelligence_profile'")

SCHEMA_SQL = rf"""
ALTER TABLE professional_profiles
    ADD COLUMN full_name      text CHECK (full_name IS NULL OR length(full_name) <= 120),
    ADD COLUMN career_stage   text NOT NULL DEFAULT 'beginner'
                              CHECK (career_stage IN ('beginner', 'experienced_freelancer', 'job_seeker', 'consultant')),
    ADD COLUMN country        text CHECK (country IS NULL OR country ~ '^[A-Z]{{2}}$'),
    ADD COLUMN city           text CHECK (city IS NULL OR length(city) <= 120),
    ADD COLUMN timezone       text CHECK (timezone IS NULL OR length(timezone) <= 64),
    ADD COLUMN currency       text CHECK (currency IS NULL OR currency ~ '^[A-Z]{{3}}$'),
    ADD COLUMN work_modes     jsonb NOT NULL DEFAULT '[]'::jsonb,  -- ["freelance","remote_full_time","contract","part_time"]
    ADD COLUMN interests      jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN services       jsonb NOT NULL DEFAULT '[]'::jsonb,  -- [{{name, description, deliverables, price, currency}}]
    ADD COLUMN portfolio      jsonb NOT NULL DEFAULT '[]'::jsonb,  -- [{{title, url, description, role, outcome}}]
    ADD COLUMN certifications jsonb NOT NULL DEFAULT '[]'::jsonb,  -- [{{name, issuer, year, url}}]
    ADD COLUMN languages      jsonb NOT NULL DEFAULT '[]'::jsonb,  -- [{{language, level}}]
    ADD COLUMN links          jsonb NOT NULL DEFAULT '[]'::jsonb,  -- [{{label, url}}]
    ADD COLUMN payment_methods jsonb NOT NULL DEFAULT '[]'::jsonb, -- ["Payoneer", "Local bank"]: what the user can receive
    ADD COLUMN availability   jsonb NOT NULL DEFAULT '{{}}'::jsonb, -- {{hours_per_week, start, overlap_note}}
    ADD COLUMN assessment     jsonb NOT NULL DEFAULT '{{}}'::jsonb, -- editable AI skills assessment
    ADD COLUMN assessment_updated_at timestamptz;

ALTER TABLE assets DROP CONSTRAINT assets_type_check;
ALTER TABLE assets ADD CONSTRAINT assets_type_check CHECK (type IN ({OLD_ASSET_TYPES}, {NEW_ASSET_TYPES}));

CREATE TABLE opportunities (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  uuid NOT NULL,
    org_id        uuid NOT NULL,
    kind          text NOT NULL CHECK (kind IN ('job', 'freelance_project', 'contract', 'internship', 'fellowship',
                                                 'grant', 'other')),
    title         text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    organisation  text NOT NULL DEFAULT '' CHECK (length(organisation) <= 200),
    url           text CHECK (url IS NULL OR (url ~ '^https?://' AND length(url) <= 2000)),
    source        text NOT NULL CHECK (source IN ('manual', 'pasted', 'integration')),
    source_name   text NOT NULL DEFAULT '' CHECK (length(source_name) <= 120),   -- "LinkedIn", "a friend"
    remote_type   text NOT NULL DEFAULT 'unknown'
                  CHECK (remote_type IN ('remote_global', 'remote_regional', 'hybrid', 'onsite', 'unknown')),
    eligible_countries jsonb NOT NULL DEFAULT '[]'::jsonb,   -- ISO 3166-1 alpha-2 codes stated by the listing
    excluded_countries jsonb NOT NULL DEFAULT '[]'::jsonb,
    location_note text NOT NULL DEFAULT '' CHECK (length(location_note) <= 500),
    timezone_requirement jsonb NOT NULL DEFAULT '{{}}'::jsonb, -- {{tz, start_hour, end_hour}} in that zone
    pay_min       numeric(14,2) CHECK (pay_min >= 0),
    pay_max       numeric(14,2) CHECK (pay_max >= 0),
    pay_currency  text CHECK (pay_currency IS NULL OR pay_currency ~ '^[A-Z]{{3}}$'),
    pay_period    text NOT NULL DEFAULT 'unknown'
                  CHECK (pay_period IN ('hour', 'day', 'week', 'month', 'year', 'project', 'unknown')),
    deadline      date,
    description   text NOT NULL DEFAULT '' CHECK (length(description) <= 20000),  -- external text: untrusted
    status        text NOT NULL DEFAULT 'unverified'
                  CHECK (status IN ('unverified', 'verified', 'expired', 'closed', 'archived')),
    verified_at   timestamptz,
    verified_by   uuid REFERENCES users(id),
    verification_note text NOT NULL DEFAULT '' CHECK (length(verification_note) <= 500),
    analysis      jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    created_by    uuid NOT NULL REFERENCES users(id),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CHECK (pay_min IS NULL OR pay_max IS NULL OR pay_max >= pay_min),
    CHECK (status <> 'verified' OR verified_at IS NOT NULL),
    UNIQUE (id, workspace_id),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE
);
CREATE INDEX opportunities_ws_idx ON opportunities (workspace_id, status, created_at DESC);

CREATE TABLE applications (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid NOT NULL,
    org_id          uuid NOT NULL,
    opportunity_id  uuid,
    title           text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    organisation    text NOT NULL DEFAULT '' CHECK (length(organisation) <= 200),
    url             text CHECK (url IS NULL OR (url ~ '^https?://' AND length(url) <= 2000)),
    status          text NOT NULL DEFAULT 'preparing'
                    CHECK (status IN ('preparing', 'applied', 'interviewing', 'offer', 'accepted', 'rejected',
                                      'withdrawn', 'no_response')),
    applied_on      date,
    next_step       text NOT NULL DEFAULT '' CHECK (length(next_step) <= 300),
    next_step_due   date,
    cv_asset_id     uuid,
    letter_asset_id uuid,
    contact         text NOT NULL DEFAULT '' CHECK (length(contact) <= 200),
    expected_pay    text NOT NULL DEFAULT '' CHECK (length(expected_pay) <= 120),
    notes           text NOT NULL DEFAULT '' CHECK (length(notes) <= 4000),
    history         jsonb NOT NULL DEFAULT '[]'::jsonb,  -- [{{at, status, note}}], appended by the server
    created_by      uuid NOT NULL REFERENCES users(id),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE,
    FOREIGN KEY (opportunity_id, workspace_id) REFERENCES opportunities(id, workspace_id)
        ON DELETE SET NULL (opportunity_id)
);
CREATE INDEX applications_ws_idx ON applications (workspace_id, status, updated_at DESC);

CREATE TABLE interview_sessions (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id   uuid NOT NULL,
    org_id         uuid NOT NULL,
    application_id uuid,
    role_title     text NOT NULL CHECK (length(role_title) BETWEEN 1 AND 200),
    questions      jsonb NOT NULL DEFAULT '[]'::jsonb,  -- [{{question, type, why_asked}}]
    answers        jsonb NOT NULL DEFAULT '[]'::jsonb,  -- [{{index, answer, feedback, run_id, at}}]
    status         text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed')),
    source_run_id  uuid,
    created_by     uuid NOT NULL REFERENCES users(id),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE
);
CREATE INDEX interview_sessions_ws_idx ON interview_sessions (workspace_id, created_at DESC);

CREATE TRIGGER opportunities_updated BEFORE UPDATE ON opportunities FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER applications_updated BEFORE UPDATE ON applications FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER interview_sessions_updated BEFORE UPDATE ON interview_sessions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
"""

TABLES = ("opportunities", "applications", "interview_sessions")


def _app_role() -> str:
    role = context.config.get_main_option("app_role") or "eco_app"
    if not role.replace("_", "").isalnum():
        raise ValueError("invalid app_role")
    return role


def upgrade() -> None:
    role = _app_role()
    op.execute(SCHEMA_SQL)
    for t in TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {t}_select ON {t} FOR SELECT USING (app.can_read_ws(workspace_id))")
        op.execute(f"CREATE POLICY {t}_write ON {t} FOR ALL USING (app.can_write_ws(workspace_id)) "
                   f"WITH CHECK (app.can_write_ws(workspace_id))")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO {role}")
        op.execute(f"REVOKE TRUNCATE ON {t} FROM {role}")


def downgrade() -> None:
    for t in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    op.execute(f"DELETE FROM asset_versions WHERE asset_id IN (SELECT id FROM assets WHERE type IN ({NEW_ASSET_TYPES}))")
    op.execute(f"DELETE FROM assets WHERE type IN ({NEW_ASSET_TYPES})")
    op.execute("ALTER TABLE assets DROP CONSTRAINT assets_type_check")
    op.execute(f"ALTER TABLE assets ADD CONSTRAINT assets_type_check CHECK (type IN ({OLD_ASSET_TYPES}))")
    op.execute("ALTER TABLE professional_profiles " + ", ".join(f"DROP COLUMN {c}" for c in (
        "full_name", "career_stage", "country", "city", "timezone", "currency", "work_modes", "interests", "services",
        "portfolio", "certifications", "languages", "links", "payment_methods", "availability", "assessment",
        "assessment_updated_at")))
