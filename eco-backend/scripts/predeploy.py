"""Pre-deploy step: runs in the NEW image, before it takes traffic (the host's "pre-deploy command").

    python -m scripts.predeploy

1. Reads the live schema revision.
2. Release gate: refuses destructive migrations unless approved for this exact revision (scripts/migration_safety).
3. If migrations are pending: takes a logical backup first (scripts/backup; needs BACKUP_S3_BUCKET in deployed envs).
4. Applies migrations (alembic upgrade head).
Any failure exits non-zero: the host then aborts the deploy and the previous release keeps serving.
"""
from __future__ import annotations

import os
import sys

import psycopg
from alembic import command
from alembic.config import Config

from scripts import backup, migration_safety


def main() -> int:
    url = os.environ.get("MIGRATIONS_DATABASE_URL")
    if not url:
        print("MIGRATIONS_DATABASE_URL is required")
        return 1
    with psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://")) as c:
        exists = c.execute("SELECT to_regclass('public.alembic_version') IS NOT NULL").fetchone()[0]
        current = c.execute("SELECT version_num FROM alembic_version").fetchone()[0] if exists else None
    print(f"live schema: {current or 'empty database'}")
    if migration_safety.main(current or "none") != 0:
        print("ABORT: release gate failed; nothing was changed")
        return 1
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "migrations"))
    from alembic.script import ScriptDirectory
    head = ScriptDirectory.from_config(cfg).get_current_head()
    if current == head:
        print(f"schema already at {head}: no migration, no backup needed")
        return 0
    if current and os.environ.get("ENV") in ("staging", "prod"):
        if not os.environ.get("BACKUP_S3_BUCKET"):
            print("ABORT: BACKUP_S3_BUCKET is required to back up before migrating")
            return 1
        backup.main(None)
    command.upgrade(cfg, "head")
    print(f"migrated {current or 'empty'} -> {head}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
