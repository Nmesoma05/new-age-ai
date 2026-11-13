"""Restore drill: prove the latest backup restores, and measure how long it takes (the recovery time).

    python -m scripts.restore_drill                      # latest backup in BACKUP_S3_BUCKET/<ENV>/
    python -m scripts.restore_drill --from-dir /tmp/b    # latest backup in a local folder
    python -m scripts.restore_drill --keep               # leave the restored database for inspection

Restores into a NEW database on RESTORE_ADMIN_URL's server (never the live one), named eco_drill_<timestamp>, then
checks: dump checksum, schema version, every table present with at least the manifest's row count, row-level
security still enabled, and the app role's grants intact. Drops the database afterwards unless --keep.
Run monthly (scheduled) and before launch. A failed drill is an incident.

Env: RESTORE_ADMIN_URL (a role that may CREATE DATABASE on the drill server, e.g. postgresql://owner@host/postgres),
ENV, BACKUP_S3_BUCKET / BACKUP_S3_ENDPOINT_URL, APP_DB_ROLE (default eco_app).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from scripts.backup import s3, sha256, table_counts


def fetch_latest(from_dir: str | None) -> tuple[Path, dict]:
    env = os.environ.get("ENV", "dev")
    if from_dir:
        manifests = sorted(Path(from_dir).glob(f"eco-{env}-*.manifest.json"))
        if not manifests:
            sys.exit(f"no backups for {env} in {from_dir}")
        m = json.loads(manifests[-1].read_text())
        return manifests[-1].parent / m["dump"], m
    bucket, cli = os.environ["BACKUP_S3_BUCKET"], s3()
    keys = sorted(o["Key"] for page in cli.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=f"{env}/")
                  for o in page.get("Contents", []) if o["Key"].endswith(".manifest.json"))
    if not keys:
        sys.exit(f"no backups in s3://{bucket}/{env}/")
    work = Path(tempfile.mkdtemp(prefix="eco-drill-"))
    m = json.loads(cli.get_object(Bucket=bucket, Key=keys[-1])["Body"].read())
    dump = work / m["dump"]
    cli.download_file(bucket, f"{env}/{m['dump']}", str(dump))
    return dump, m


def main(from_dir: str | None, keep: bool) -> int:
    admin = os.environ["RESTORE_ADMIN_URL"].replace("postgresql+psycopg://", "postgresql://")
    role = os.environ.get("APP_DB_ROLE", "eco_app")
    t0 = time.time()
    dump, m = fetch_latest(from_dir)
    problems: list[str] = []
    if sha256(dump) != m["sha256"]:
        sys.exit("FAIL: dump checksum doesn't match its manifest (corrupt or tampered)")
    name = f"eco_drill_{datetime.now(UTC):%Y%m%d%H%M%S}"
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{name}"')
    target = admin.rsplit("/", 1)[0] + f"/{name}"
    try:
        r = subprocess.run(["pg_restore", "--exit-on-error", "--no-comments", "--no-password", f"--dbname={target}", str(dump)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            problems.append(f"pg_restore failed: {r.stderr.strip()[:500]}")
        else:
            version, counts = table_counts(target)
            if version != m["schema_version"]:
                problems.append(f"schema version {version} != {m['schema_version']}")
            for t, n in m["tables"].items():
                if t not in counts:
                    problems.append(f"table missing: {t}")
                elif counts[t] < n:
                    problems.append(f"{t}: {counts[t]} rows < {n} in manifest")
            with psycopg.connect(target) as c:
                no_rls = [r[0] for r in c.execute(
                    "SELECT relname FROM pg_class WHERE relkind='r' AND relnamespace='public'::regnamespace "
                    "AND relname IN ('workspaces','assets','documents','messages','memory_items','integrations') "
                    "AND NOT relrowsecurity")]
                if no_rls:
                    problems.append(f"row-level security off after restore: {no_rls}")
                if not c.execute("SELECT has_table_privilege(%s, 'workspaces', 'SELECT')", (role,)).fetchone()[0]:
                    problems.append(f"grants for {role} were not restored")
        took = time.time() - t0
        rows = sum(m["tables"].values())
        if problems:
            print("RESTORE DRILL FAILED\n  " + "\n  ".join(problems))
        else:
            print(f"RESTORE DRILL PASSED: backup {m['created_at']} ({m['env']}, release {m['release']}), "
                  f"{len(m['tables'])} tables, {rows} rows, schema {m['schema_version']}, restored in {took:.1f}s "
                  f"into {name}")
    finally:
        if not keep:
            with psycopg.connect(admin, autocommit=True) as c:
                c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    return 1 if problems else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-dir")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    sys.exit(main(a.from_dir, a.keep))
