"""Permanently erase organisations closed by account deletion, after the grace period. Run daily (cron/scheduler).

    python -m scripts.purge_deleted            # dry run: lists what would be erased
    python -m scripts.purge_deleted --apply    # erase

Uses MIGRATIONS_DATABASE_URL (the schema owner, like migrations). For each organisation soft-deleted more than
PURGE_AFTER_DAYS ago (default 30): delete its files under org/<id>/ in storage, then delete the organisation row,
which cascades to its workspaces and everything in them. Audit events stay, with org_id cleared (the trigger allows
only that). Files are deleted before rows, so a crash halfway leaves rows to retry, never orphaned files.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

import psycopg

from app.core.config import get_settings
from app.services.storage import get_storage


def _dsn() -> str:
    url = os.environ.get("MIGRATIONS_DATABASE_URL") or get_settings().database_url.get_secret_value()
    return url.replace("postgresql+psycopg://", "postgresql://")


async def main(apply: bool, days: int) -> int:
    with psycopg.connect(_dsn(), autocommit=True) as c:
        rows = c.execute("SELECT id, name, deleted_at FROM organisations WHERE deleted_at IS NOT NULL "
                         "AND deleted_at < now() - make_interval(days => %s) ORDER BY deleted_at", (days,)).fetchall()
        print(f"{len(rows)} organisation(s) closed more than {days} days ago")
        for org_id, _name, deleted_at in rows:
            if not apply:
                print(f"  would erase {org_id} (closed {deleted_at:%Y-%m-%d})")
                continue
            files = await get_storage().delete_prefix(f"org/{org_id}/")
            with c.transaction():
                c.execute("DELETE FROM organisations WHERE id = %s AND deleted_at IS NOT NULL", (org_id,))
                c.execute("INSERT INTO audit_events (action, target_type, target_id, metadata) VALUES "
                          "('org.purged', 'organisation', %s, jsonb_build_object('files', %s::int))",
                          (str(org_id), files))
            print(f"  erased {org_id}: {files} file(s)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--days", type=int, default=int(os.environ.get("PURGE_AFTER_DAYS", "30")))
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.apply, a.days)))
