"""Tenant isolation: grants for the application role, helper functions and row-level security.

The application connects as a non-owner role (default ``eco_app``) without BYPASSRLS.
Each transaction sets ``app.user_id`` and ``app.context`` with set_config(..., true).
``app.context = 'system'`` is reserved for narrow server-side paths (auth, webhooks, usage counters).

Revision ID: 0002_rls_policies
Revises: 0001_core_schema
"""
from alembic import context, op

revision = "0002_rls_policies"
down_revision = "0001_core_schema"
branch_labels = None
depends_on = None

WORKSPACE_TABLES = [
    "projects", "client_accounts", "business_profiles", "professional_profiles", "documents",
    "conversations", "messages", "assets", "asset_versions",
]
ALL_TABLES = [
    "users", "refresh_tokens", "organisations", "org_members", "teams", "team_members", "product_access",
    "plans", "subscriptions", "usage_counters", "webhook_events", "workspaces", "workspace_members",
    "ai_usage_records", "integrations", "audit_events", *WORKSPACE_TABLES,
]


def _app_role() -> str:
    role = context.config.get_main_option("app_role") or "eco_app"
    if not role.replace("_", "").isalnum():
        raise ValueError("invalid app_role")
    return role


FUNCTIONS_SQL = r"""
CREATE SCHEMA IF NOT EXISTS app;

CREATE FUNCTION app.uid() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT NULLIF(current_setting('app.user_id', true), '')::uuid $$;

CREATE FUNCTION app.is_system() RETURNS boolean LANGUAGE sql STABLE AS
$$ SELECT coalesce(current_setting('app.context', true), '') = 'system' $$;

CREATE FUNCTION app.org_role(p_org uuid) RETURNS text LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp AS
$$ SELECT role FROM org_members WHERE org_id = p_org AND user_id = app.uid() $$;

CREATE FUNCTION app.is_org_member(p_org uuid) RETURNS boolean LANGUAGE sql STABLE AS
$$ SELECT app.org_role(p_org) IS NOT NULL $$;

CREATE FUNCTION app.is_org_admin(p_org uuid) RETURNS boolean LANGUAGE sql STABLE AS
$$ SELECT coalesce(app.org_role(p_org) IN ('owner', 'admin'), false) $$;

-- Effective workspace role: org owners/admins are implicit workspace admins.
CREATE FUNCTION app.ws_role(p_ws uuid) RETURNS text LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp AS
$$
    SELECT CASE WHEN om.role IN ('owner', 'admin') THEN 'admin' ELSE wm.role END
    FROM workspaces w
    JOIN org_members om ON om.org_id = w.org_id AND om.user_id = app.uid()
    LEFT JOIN workspace_members wm ON wm.workspace_id = w.id AND wm.user_id = app.uid()
    WHERE w.id = p_ws AND w.deleted_at IS NULL
$$;

CREATE FUNCTION app.can_read_ws(p_ws uuid) RETURNS boolean LANGUAGE sql STABLE AS
$$ SELECT app.is_system() OR coalesce(app.ws_role(p_ws) IN ('admin', 'editor', 'viewer'), false) $$;

CREATE FUNCTION app.can_write_ws(p_ws uuid) RETURNS boolean LANGUAGE sql STABLE AS
$$ SELECT app.is_system() OR coalesce(app.ws_role(p_ws) IN ('admin', 'editor'), false) $$;

CREATE FUNCTION app.shares_org(p_user uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp AS
$$ SELECT EXISTS (SELECT 1 FROM org_members a JOIN org_members b ON a.org_id = b.org_id
                  WHERE a.user_id = app.uid() AND b.user_id = p_user) $$;

CREATE FUNCTION app.owns_org_record(p_org uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp AS
$$ SELECT EXISTS (SELECT 1 FROM organisations WHERE id = p_org AND owner_user_id = app.uid()) $$;

REVOKE ALL ON FUNCTION app.org_role(uuid), app.ws_role(uuid), app.shares_org(uuid), app.owns_org_record(uuid) FROM PUBLIC;
"""

POLICIES_SQL = r"""
-- identity
CREATE POLICY users_select ON users FOR SELECT USING (app.is_system() OR id = app.uid() OR app.shares_org(id));
CREATE POLICY users_insert ON users FOR INSERT WITH CHECK (app.is_system());
CREATE POLICY users_update ON users FOR UPDATE USING (app.is_system() OR id = app.uid()) WITH CHECK (app.is_system() OR id = app.uid());
CREATE POLICY users_delete ON users FOR DELETE USING (app.is_system());
CREATE POLICY refresh_tokens_all ON refresh_tokens USING (app.is_system()) WITH CHECK (app.is_system());

-- organisations and membership
CREATE POLICY orgs_select ON organisations FOR SELECT USING (app.is_system() OR app.is_org_member(id) OR owner_user_id = app.uid());
CREATE POLICY orgs_insert ON organisations FOR INSERT WITH CHECK (app.is_system() OR owner_user_id = app.uid());
CREATE POLICY orgs_update ON organisations FOR UPDATE USING (app.is_system() OR app.is_org_admin(id)) WITH CHECK (app.is_system() OR app.is_org_admin(id));
CREATE POLICY orgs_delete ON organisations FOR DELETE USING (app.is_system() OR app.org_role(id) = 'owner');

CREATE POLICY org_members_select ON org_members FOR SELECT USING (app.is_system() OR user_id = app.uid() OR app.is_org_member(org_id));
CREATE POLICY org_members_insert ON org_members FOR INSERT WITH CHECK (
    app.is_system() OR app.is_org_admin(org_id)
    OR (user_id = app.uid() AND role = 'owner' AND app.owns_org_record(org_id)));
CREATE POLICY org_members_update ON org_members FOR UPDATE USING (app.is_system() OR app.is_org_admin(org_id)) WITH CHECK (app.is_system() OR app.is_org_admin(org_id));
CREATE POLICY org_members_delete ON org_members FOR DELETE USING (app.is_system() OR app.is_org_admin(org_id));

CREATE POLICY teams_select ON teams FOR SELECT USING (app.is_system() OR app.is_org_member(org_id));
CREATE POLICY teams_write ON teams FOR ALL USING (app.is_system() OR app.is_org_admin(org_id)) WITH CHECK (app.is_system() OR app.is_org_admin(org_id));
CREATE POLICY team_members_select ON team_members FOR SELECT USING (app.is_system() OR app.is_org_member(org_id));
CREATE POLICY team_members_write ON team_members FOR ALL USING (app.is_system() OR app.is_org_admin(org_id)) WITH CHECK (app.is_system() OR app.is_org_admin(org_id));

CREATE POLICY product_access_select ON product_access FOR SELECT USING (app.is_system() OR app.is_org_member(org_id));
CREATE POLICY product_access_write ON product_access FOR ALL USING (app.is_system() OR app.is_org_admin(org_id)) WITH CHECK (app.is_system() OR app.is_org_admin(org_id));

-- billing: readable by members, writable only by server-side system paths
CREATE POLICY plans_select ON plans FOR SELECT USING (true);
CREATE POLICY subscriptions_select ON subscriptions FOR SELECT USING (app.is_system() OR app.is_org_member(org_id));
CREATE POLICY subscriptions_write ON subscriptions FOR ALL USING (app.is_system()) WITH CHECK (app.is_system());
CREATE POLICY usage_counters_select ON usage_counters FOR SELECT USING (app.is_system() OR app.is_org_member(org_id));
CREATE POLICY usage_counters_write ON usage_counters FOR ALL USING (app.is_system()) WITH CHECK (app.is_system());
CREATE POLICY webhook_events_all ON webhook_events USING (app.is_system()) WITH CHECK (app.is_system());

-- workspaces
CREATE POLICY workspaces_select ON workspaces FOR SELECT USING (app.is_system() OR app.is_org_admin(org_id) OR app.ws_role(id) IN ('admin', 'editor', 'viewer'));
CREATE POLICY workspaces_insert ON workspaces FOR INSERT WITH CHECK (app.is_system() OR (app.is_org_admin(org_id) AND created_by = app.uid()));
CREATE POLICY workspaces_update ON workspaces FOR UPDATE USING (app.is_system() OR app.ws_role(id) = 'admin') WITH CHECK (app.is_system() OR app.is_org_admin(org_id) OR app.ws_role(id) = 'admin');
CREATE POLICY workspaces_delete ON workspaces FOR DELETE USING (app.is_system() OR app.org_role(org_id) = 'owner');

CREATE POLICY workspace_members_select ON workspace_members FOR SELECT USING (app.can_read_ws(workspace_id) OR user_id = app.uid());
CREATE POLICY workspace_members_write ON workspace_members FOR ALL USING (app.is_system() OR app.ws_role(workspace_id) = 'admin') WITH CHECK (app.is_system() OR app.ws_role(workspace_id) = 'admin');

-- usage records: members insert their own; admins and the user can read
CREATE POLICY ai_usage_select ON ai_usage_records FOR SELECT USING (app.is_system() OR app.is_org_admin(org_id) OR user_id = app.uid());
CREATE POLICY ai_usage_insert ON ai_usage_records FOR INSERT WITH CHECK (app.is_system() OR (user_id = app.uid() AND app.is_org_member(org_id)));

-- integrations: admins only (credentials are encrypted and never returned by the API)
CREATE POLICY integrations_all ON integrations USING (app.is_system() OR app.is_org_admin(org_id)) WITH CHECK (app.is_system() OR app.is_org_admin(org_id));

-- audit log: admins read; members and system append
CREATE POLICY audit_select ON audit_events FOR SELECT USING (app.is_system() OR app.is_org_admin(org_id));
CREATE POLICY audit_insert ON audit_events FOR INSERT WITH CHECK (
    app.is_system() OR (actor_user_id = app.uid() AND (org_id IS NULL OR app.is_org_member(org_id))));
"""


def upgrade() -> None:
    role = _app_role()
    op.execute(FUNCTIONS_SQL)
    op.execute(POLICIES_SQL)
    for t in WORKSPACE_TABLES:
        op.execute(f"CREATE POLICY {t}_select ON {t} FOR SELECT USING (app.can_read_ws(workspace_id))")
        op.execute(f"CREATE POLICY {t}_insert ON {t} FOR INSERT WITH CHECK (app.can_write_ws(workspace_id))")
        op.execute(f"CREATE POLICY {t}_update ON {t} FOR UPDATE USING (app.can_write_ws(workspace_id)) WITH CHECK (app.can_write_ws(workspace_id))")
        op.execute(f"CREATE POLICY {t}_delete ON {t} FOR DELETE USING (app.can_write_ws(workspace_id))")
    for t in ALL_TABLES:
        # RLS is not FORCEd: the table owner (migration role) stays exempt so the SECURITY DEFINER
        # helpers can read membership tables. The application role is never the owner (tested).
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")

    op.execute(f"GRANT USAGE ON SCHEMA public, app TO {role}")
    op.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO {role}")
    rw = [t for t in ALL_TABLES if t not in ("audit_events", "plans")]
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(rw)} TO {role}")
    op.execute(f"GRANT SELECT ON plans TO {role}")
    op.execute(f"GRANT SELECT, INSERT ON audit_events TO {role}")
    op.execute(f"REVOKE TRUNCATE ON ALL TABLES IN SCHEMA public FROM {role}")


def downgrade() -> None:
    role = _app_role()
    for t in ALL_TABLES:
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
        op.execute(f"DO $$ DECLARE p record; BEGIN FOR p IN SELECT policyname FROM pg_policies WHERE tablename = '{t}' LOOP "
                   f"EXECUTE format('DROP POLICY %I ON {t}', p.policyname); END LOOP; END $$;")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}")
    op.execute("DROP SCHEMA IF EXISTS app CASCADE")
