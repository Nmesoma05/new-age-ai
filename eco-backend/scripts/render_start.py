"""Render start step for the API (preview): prepare the database, migrate, then run the API as the restricted role.

    python -m scripts.render_start

Render gives one database user (the "default" user, not a superuser). We use it as the OWNER role, which runs
migrations, and create the restricted app role (eco_app: no BYPASSRLS, so row-level security applies) from it.

Env:
  OWNER_DATABASE_URL  Render's internal connection string for the database (fromDatabase connectionString)
  APP_DB_PASSWORD     password for eco_app (Render generateValue)
The API process gets DATABASE_URL for eco_app only; it never connects as the owner.
Any failure exits non-zero before the API starts, so Render keeps the previous release serving.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from psycopg import sql

APP_ROLE = "eco_app"


def _with_driver(url: str) -> str:
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def app_url(owner_url: str, password: str) -> str:
    """The owner URL with eco_app's credentials swapped in (host, port, database and query kept)."""
    u = urlsplit(_with_driver(owner_url))
    host = u.hostname or ""
    netloc = f"{APP_ROLE}:{quote(password, safe='')}@{host}" + (f":{u.port}" if u.port else "")
    return urlunsplit((u.scheme, netloc, u.path, u.query, ""))


def ensure_roles(owner_url: str, password: str) -> None:
    with psycopg.connect(owner_url.replace("postgresql+psycopg://", "postgresql://"), autocommit=True) as c:
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")
        c.execute("CREATE EXTENSION IF NOT EXISTS citext")
        exists = c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,)).fetchone()
        # name and password go through psycopg quoting, never string formatting. Only LOGIN + PASSWORD are set:
        # the defaults (NOSUPERUSER NOCREATEROLE NOBYPASSRLS) are exactly what we need, and a non-superuser
        # owner may not be allowed to name those attributes at all. They are checked below instead.
        verb = "ALTER ROLE {} PASSWORD {}" if exists else "CREATE ROLE {} LOGIN PASSWORD {}"
        c.execute(sql.SQL(verb).format(sql.Identifier(APP_ROLE), sql.Literal(password)))
        su, rls, cr = c.execute("SELECT rolsuper, rolbypassrls, rolcreaterole FROM pg_roles WHERE rolname = %s",
                                (APP_ROLE,)).fetchone()
        if su or rls or cr:
            raise SystemExit(f"ABORT: {APP_ROLE} has superuser, BYPASSRLS or CREATEROLE; row-level security would "
                             "not protect tenants")
        db = c.execute("SELECT current_database()").fetchone()[0]
        db = db.decode() if isinstance(db, bytes) else db  # SQL_ASCII clusters return bytes
        c.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(db), sql.Identifier(APP_ROLE)))
    print(f"database ready: role {APP_ROLE} {'updated' if exists else 'created'}")


def main() -> int:
    owner, pw = os.environ.get("OWNER_DATABASE_URL"), os.environ.get("APP_DB_PASSWORD")
    if not owner or not pw:
        print("OWNER_DATABASE_URL and APP_DB_PASSWORD are required")
        return 1
    ensure_roles(owner, pw)
    os.environ["MIGRATIONS_DATABASE_URL"] = _with_driver(owner)
    from scripts import predeploy
    if predeploy.main() != 0:
        return 1
    env = {k: v for k, v in os.environ.items() if k not in ("OWNER_DATABASE_URL", "MIGRATIONS_DATABASE_URL")}
    env["DATABASE_URL"] = app_url(owner, pw)
    workers = env.get("WEB_CONCURRENCY", "2")
    port = env.get("PORT", "8000")
    os.execvpe("uvicorn", ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", port, "--workers", workers,
                           "--no-proxy-headers", "--no-server-header", "--timeout-graceful-shutdown", "25"], env)
    return 0  # not reached


if __name__ == "__main__":
    sys.exit(main())
