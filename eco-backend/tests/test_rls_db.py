"""Row-level security tested directly at the database, as the application role.

These prove that a missed tenant filter in application code still cannot leak or modify another tenant's rows.
"""
import psycopg
import pytest

from tests.conftest import APP_DSN


def app_conn(user_id=None, context="user"):
    c = psycopg.connect(APP_DSN, autocommit=False)
    c.execute("SELECT set_config('app.user_id', %s, true), set_config('app.context', %s, true)",
              (str(user_id) if user_id else "", context))
    return c


async def _seed(client, signup, make_workspace):
    a, b = await signup("Ada"), await signup("Bola")
    ws = await make_workspace(a)
    await client.post(f"/v1/workspaces/{ws}/assets", headers=a.h, json={"type": "post", "title": "A only", "body": {}})
    conv = (await client.post(f"/v1/workspaces/{ws}/conversations", headers=a.h, json={})).json()
    return a, b, ws, conv


TENANT_TABLES = ["workspaces", "assets", "asset_versions", "conversations", "org_members", "organisations",
                 "product_access", "audit_events"]


async def test_unfiltered_selects_return_only_own_rows(client, signup, make_workspace):
    a, b, ws, conv = await _seed(client, signup, make_workspace)
    with app_conn(b.user_id) as c:
        for t in TENANT_TABLES:
            rows = c.execute(f"SELECT * FROM {t} WHERE org_id = %s" if t != "organisations"
                             else f"SELECT * FROM {t} WHERE id = %s", (a.org_id,)).fetchall()
            assert rows == [], t
        assert c.execute("SELECT count(*) FROM users WHERE id = %s", (a.user_id,)).fetchone()[0] == 0
    with app_conn(a.user_id) as c:
        assert c.execute("SELECT count(*) FROM assets").fetchone()[0] == 1


async def test_anonymous_sees_nothing(client, signup, make_workspace):
    await _seed(client, signup, make_workspace)
    with app_conn(None) as c:
        for t in TENANT_TABLES + ["users", "refresh_tokens", "subscriptions", "integrations"]:
            assert c.execute(f"SELECT count(*) FROM {t}").fetchone()[0] == 0, t


async def test_cross_tenant_insert_and_update_are_blocked(client, signup, make_workspace):
    a, b, ws, conv = await _seed(client, signup, make_workspace)
    with app_conn(b.user_id) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("INSERT INTO assets (workspace_id, org_id, type, title, created_by) VALUES (%s, %s, 'post', 'x', %s)",
                      (ws, a.org_id, b.user_id))
    with app_conn(b.user_id) as c:
        n = c.execute("UPDATE assets SET title = 'hacked' WHERE workspace_id = %s", (ws,)).rowcount
        assert n == 0
        n = c.execute("DELETE FROM conversations WHERE id = %s", (conv["id"],)).rowcount
        assert n == 0
    with app_conn(b.user_id) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("INSERT INTO org_members (org_id, user_id, role) VALUES (%s, %s, 'admin')", (a.org_id, b.user_id))


async def test_users_cannot_grant_themselves_paid_plans_or_reset_usage(client, signup):
    a = await signup("Ada")
    with app_conn(a.user_id) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("INSERT INTO subscriptions (org_id, plan_code, status, provider, period_start, period_end) "
                      "VALUES (%s, 'pro', 'active', 'manual', now(), now() + interval '1 year')", (a.org_id,))
    with app_conn(a.user_id) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("INSERT INTO usage_counters (org_id, period_month, free_generations_used) "
                      "VALUES (%s, date_trunc('month', now())::date, 0)", (a.org_id,))


def test_app_role_is_not_owner_and_cannot_bypass_rls(owner_db):
    from tests.conftest import APP
    row = owner_db.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s", (APP,)).fetchone()
    assert row == (False, False)
    owners = {r[0] for r in owner_db.execute("SELECT tableowner FROM pg_tables WHERE schemaname = 'public'")}
    assert APP not in owners
    no_rls = [r[0] for r in owner_db.execute(
        "SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r' "
        "AND NOT relrowsecurity AND relname <> 'alembic_version'")]
    assert no_rls == []


async def test_audit_log_is_append_only(client, signup, owner_db):
    await signup("Ada")
    with app_conn(None, context="system") as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("UPDATE audit_events SET action = 'x.y'")
    with app_conn(None, context="system") as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("DELETE FROM audit_events")
    # even the table owner cannot rewrite history (trigger)
    with pytest.raises(psycopg.errors.RaiseException):
        owner_db.execute("UPDATE audit_events SET action = 'tampered.event'")
