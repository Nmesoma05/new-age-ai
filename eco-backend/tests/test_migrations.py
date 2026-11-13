"""Migrations are the source of truth; models must match them, and migrations must reverse cleanly."""
import os
import secrets

import psycopg

from tests.conftest import HOST, OWNER, OWNER_DSN, OWNER_PW


def test_models_match_migrated_schema():
    from app.models import Base
    with psycopg.connect(OWNER_DSN) as c:
        db = {}
        for table, col, nullable in c.execute(
                "SELECT table_name, column_name, is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"):
            db.setdefault(table, {})[col] = nullable == "YES"
    models = {t.name: {c.name: c.nullable for c in t.columns} for t in Base.metadata.sorted_tables}
    assert set(models) == set(db), set(models) ^ set(db)
    for t, cols in models.items():
        assert cols == db[t], (t, {k: (cols.get(k), db[t].get(k)) for k in set(cols) | set(db[t]) if cols.get(k) != db[t].get(k)})


def test_upgrade_downgrade_upgrade():
    from alembic import command
    from alembic.config import Config
    name = f"eco_mig_{secrets.token_hex(4)}"
    with psycopg.connect(f"postgresql://{OWNER}:{OWNER_PW}@{HOST}/postgres", autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{name}"')
    old = os.environ["MIGRATIONS_DATABASE_URL"]
    os.environ["MIGRATIONS_DATABASE_URL"] = f"postgresql+psycopg://{OWNER}:{OWNER_PW}@{HOST}/{name}"
    try:
        here = os.path.dirname(__file__)
        cfg = Config(os.path.join(here, "..", "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(here, "..", "migrations"))
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
    finally:
        os.environ["MIGRATIONS_DATABASE_URL"] = old
        with psycopg.connect(f"postgresql://{OWNER}:{OWNER_PW}@{HOST}/postgres", autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
