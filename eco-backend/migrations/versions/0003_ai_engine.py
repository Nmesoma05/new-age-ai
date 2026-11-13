"""AI engine: memory, document chunks for retrieval, agent runs, tool calls and approval-gated actions.

Needs the pgvector extension. On managed Postgres (e.g. Supabase) enable "vector" in the dashboard first;
self-hosted, a superuser runs CREATE EXTENSION vector once. This migration only checks for it.

Revision ID: 0003_ai_engine
Revises: 0002_rls_policies
"""
from alembic import context, op

revision = "0003_ai_engine"
down_revision = "0002_rls_policies"
branch_labels = None
depends_on = None

NEW_WS_TABLES = ["memory_items", "document_chunks", "agent_runs", "tool_calls", "pending_actions"]

SCHEMA_SQL = r"""
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'pgvector is not installed in this database: run CREATE EXTENSION vector as a superuser';
    END IF;
END $$;

ALTER TABLE documents ADD COLUMN text_status text NOT NULL DEFAULT 'none'
    CHECK (text_status IN ('none', 'ready', 'unsupported', 'failed'));
ALTER TABLE conversations ADD COLUMN summary text NOT NULL DEFAULT '';
ALTER TABLE conversations ADD COLUMN summary_through timestamptz;
ALTER TABLE documents ADD CONSTRAINT documents_id_ws_uq UNIQUE (id, workspace_id);

-- ------------------------------------------------------------ agent runs (one per user request)
CREATE TABLE agent_runs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid NOT NULL,
    org_id          uuid NOT NULL,
    conversation_id uuid,
    user_id         uuid NOT NULL REFERENCES users(id),
    agent           text NOT NULL,
    status          text NOT NULL CHECK (status IN ('succeeded', 'failed', 'clarify', 'unsupported', 'blocked')),
    route           jsonb NOT NULL DEFAULT '{}'::jsonb,
    output          jsonb,
    warnings        jsonb NOT NULL DEFAULT '[]'::jsonb,
    uncertainties   jsonb NOT NULL DEFAULT '[]'::jsonb,
    tainted         boolean NOT NULL DEFAULT false,
    injection_flags jsonb NOT NULL DEFAULT '[]'::jsonb,
    error_code      text,
    llm_calls       integer NOT NULL DEFAULT 0 CHECK (llm_calls >= 0),
    tokens_in       integer NOT NULL DEFAULT 0 CHECK (tokens_in >= 0),
    tokens_out      integer NOT NULL DEFAULT 0 CHECK (tokens_out >= 0),
    counted_free    boolean NOT NULL DEFAULT false,
    latency_ms      integer NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT agent_runs_id_ws_uq UNIQUE (id, workspace_id),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE,
    FOREIGN KEY (conversation_id, workspace_id) REFERENCES conversations(id, workspace_id) ON DELETE SET NULL (conversation_id)
);
CREATE INDEX agent_runs_ws_idx ON agent_runs (workspace_id, created_at DESC, id DESC);
CREATE INDEX agent_runs_user_time_idx ON agent_runs (user_id, created_at);

ALTER TABLE ai_usage_records ADD COLUMN run_id uuid REFERENCES agent_runs(id) ON DELETE SET NULL;
CREATE INDEX ai_usage_run_idx ON ai_usage_records (run_id);
ALTER TABLE messages ADD COLUMN run_id uuid REFERENCES agent_runs(id) ON DELETE SET NULL;

-- ------------------------------------------------------------ tool calls (what the agents did)
CREATE TABLE tool_calls (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id       uuid NOT NULL,
    workspace_id uuid NOT NULL,
    org_id       uuid NOT NULL,
    agent        text NOT NULL,
    tool         text NOT NULL,
    args         jsonb NOT NULL DEFAULT '{}'::jsonb,
    status       text NOT NULL CHECK (status IN ('ok', 'error', 'denied')),
    error_code   text,
    untrusted    boolean NOT NULL DEFAULT false,
    result_meta  jsonb NOT NULL DEFAULT '{}'::jsonb,  -- refs and counts only, never full content
    latency_ms   integer NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
    created_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (run_id, workspace_id) REFERENCES agent_runs(id, workspace_id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE
);
CREATE INDEX tool_calls_run_idx ON tool_calls (run_id, created_at);

-- ------------------------------------------------------------ memory (workspace-bound, never cross-workspace)
CREATE TABLE memory_items (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid NOT NULL,
    org_id          uuid NOT NULL,
    project_id      uuid,
    visibility      text NOT NULL DEFAULT 'workspace' CHECK (visibility IN ('workspace', 'private')),
    owner_user_id   uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind            text NOT NULL CHECK (kind IN ('fact', 'preference', 'decision', 'brand_rule', 'constraint')),
    content         text NOT NULL CHECK (length(content) BETWEEN 1 AND 1000),
    source          text NOT NULL CHECK (source IN ('user_stated', 'user_confirmed', 'agent_proposed')),
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'proposed', 'archived')),
    source_run_id   uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
    tsv             tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    embedding       vector(1536),
    embedding_model text,
    last_used_at    timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id, workspace_id) REFERENCES projects(id, workspace_id) ON DELETE SET NULL (project_id)
);
CREATE INDEX memory_ws_idx ON memory_items (workspace_id, status, created_at DESC);
CREATE INDEX memory_tsv_idx ON memory_items USING gin (tsv);
CREATE INDEX memory_embedding_idx ON memory_items USING hnsw (embedding vector_cosine_ops);

-- ------------------------------------------------------------ document chunks (retrieval)
CREATE TABLE document_chunks (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     uuid NOT NULL,
    workspace_id    uuid NOT NULL,
    org_id          uuid NOT NULL,
    chunk_index     integer NOT NULL CHECK (chunk_index >= 0),
    text            text NOT NULL CHECK (length(text) BETWEEN 1 AND 8000),
    char_start      integer NOT NULL DEFAULT 0,
    tsv             tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
    embedding       vector(1536),
    embedding_model text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT document_chunks_uq UNIQUE (document_id, chunk_index),
    FOREIGN KEY (document_id, workspace_id) REFERENCES documents(id, workspace_id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE
);
CREATE INDEX document_chunks_ws_idx ON document_chunks (workspace_id);
CREATE INDEX document_chunks_tsv_idx ON document_chunks USING gin (tsv);
CREATE INDEX document_chunks_embedding_idx ON document_chunks USING hnsw (embedding vector_cosine_ops);

-- ------------------------------------------------------------ external actions: proposed by agents, decided by people
CREATE TABLE pending_actions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid NOT NULL,
    org_id          uuid NOT NULL,
    run_id          uuid,
    kind            text NOT NULL CHECK (kind IN ('publish_post', 'send_message', 'spend_money')),
    integration_id  uuid REFERENCES integrations(id) ON DELETE SET NULL,
    title           text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    payload         jsonb NOT NULL,
    status          text NOT NULL DEFAULT 'awaiting_approval'
                    CHECK (status IN ('awaiting_approval', 'approved', 'rejected', 'executed', 'failed', 'expired')),
    from_untrusted  boolean NOT NULL DEFAULT false,  -- the proposing run had read documents or web content
    requested_by    uuid NOT NULL REFERENCES users(id),
    decided_by      uuid REFERENCES users(id),
    decided_at      timestamptz,
    executed_at     timestamptz,
    result          jsonb NOT NULL DEFAULT '{}'::jsonb,
    expires_at      timestamptz NOT NULL DEFAULT now() + interval '7 days',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CHECK ((status IN ('awaiting_approval', 'expired')) = (decided_by IS NULL)),
    FOREIGN KEY (workspace_id, org_id) REFERENCES workspaces(id, org_id) ON DELETE CASCADE,
    -- deferred: an agent proposes mid-run, and the run row is written at the end of the same transaction
    FOREIGN KEY (run_id, workspace_id) REFERENCES agent_runs(id, workspace_id) ON DELETE SET NULL (run_id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX pending_actions_ws_idx ON pending_actions (workspace_id, status, created_at DESC);

CREATE TRIGGER memory_items_updated BEFORE UPDATE ON memory_items FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER pending_actions_updated BEFORE UPDATE ON pending_actions FOR EACH ROW EXECUTE FUNCTION set_updated_at();
"""

POLICIES_SQL = r"""
-- memory: private items are visible only to their author, even to org admins
CREATE POLICY memory_select ON memory_items FOR SELECT
    USING (app.can_read_ws(workspace_id) AND (visibility = 'workspace' OR owner_user_id = app.uid()));
CREATE POLICY memory_insert ON memory_items FOR INSERT
    WITH CHECK (app.can_write_ws(workspace_id) AND owner_user_id = app.uid());
CREATE POLICY memory_update ON memory_items FOR UPDATE
    USING (app.can_write_ws(workspace_id) AND (visibility = 'workspace' OR owner_user_id = app.uid()))
    WITH CHECK (app.can_write_ws(workspace_id) AND (visibility = 'workspace' OR owner_user_id = app.uid()));
CREATE POLICY memory_delete ON memory_items FOR DELETE
    USING (app.can_write_ws(workspace_id) AND (visibility = 'workspace' OR owner_user_id = app.uid()));

CREATE POLICY document_chunks_select ON document_chunks FOR SELECT USING (app.can_read_ws(workspace_id));
CREATE POLICY document_chunks_write ON document_chunks FOR ALL
    USING (app.can_write_ws(workspace_id)) WITH CHECK (app.can_write_ws(workspace_id));

CREATE POLICY agent_runs_select ON agent_runs FOR SELECT USING (app.can_read_ws(workspace_id));
CREATE POLICY agent_runs_insert ON agent_runs FOR INSERT
    WITH CHECK (app.can_write_ws(workspace_id) AND user_id = app.uid());
CREATE POLICY tool_calls_select ON tool_calls FOR SELECT USING (app.can_read_ws(workspace_id));
CREATE POLICY tool_calls_insert ON tool_calls FOR INSERT WITH CHECK (app.can_write_ws(workspace_id));

-- actions: editors may propose; only workspace admins (incl. org owners/admins) may decide
CREATE POLICY pending_actions_select ON pending_actions FOR SELECT USING (app.can_read_ws(workspace_id));
CREATE POLICY pending_actions_insert ON pending_actions FOR INSERT
    WITH CHECK (app.can_write_ws(workspace_id) AND requested_by = app.uid() AND status = 'awaiting_approval');
CREATE POLICY pending_actions_update ON pending_actions FOR UPDATE
    USING (app.is_system() OR app.ws_role(workspace_id) = 'admin' OR app.is_org_admin(org_id))
    WITH CHECK (app.is_system() OR app.ws_role(workspace_id) = 'admin' OR app.is_org_admin(org_id));
"""


def _app_role() -> str:
    role = context.config.get_main_option("app_role") or "eco_app"
    if not role.replace("_", "").isalnum():
        raise ValueError("invalid app_role")
    return role


def upgrade() -> None:
    role = _app_role()
    op.execute(SCHEMA_SQL)
    op.execute(POLICIES_SQL)
    for t in NEW_WS_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON memory_items, document_chunks, pending_actions TO {role}")
    # runs and tool calls are an append-only record for the application role
    op.execute(f"GRANT SELECT, INSERT ON agent_runs, tool_calls TO {role}")
    op.execute(f"REVOKE TRUNCATE ON {', '.join(NEW_WS_TABLES)} FROM {role}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pending_actions, document_chunks, memory_items, tool_calls CASCADE")
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS run_id")
    op.execute("ALTER TABLE ai_usage_records DROP COLUMN IF EXISTS run_id")
    op.execute("DROP TABLE IF EXISTS agent_runs CASCADE")
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_id_ws_uq")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS summary_through")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS summary")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS text_status")
