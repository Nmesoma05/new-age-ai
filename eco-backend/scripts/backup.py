"""Logical backup of the database, as a second line behind the provider's point-in-time recovery.

    python -m scripts.backup                 # dump + manifest -> BACKUP_S3_BUCKET (or --out-dir), prune old ones
    python -m scripts.backup --out-dir /tmp/b

What it writes (names share a UTC timestamp):
  eco-<env>-<ts>.dump           pg_dump custom format (compressed; includes RLS policies and grants)
  eco-<env>-<ts>.manifest.json  schema version, row count per table, sha256 and size of the dump, release
The manifest is what the restore drill checks a restore against. Uploads use server-side encryption; the bucket must
be private, versioned, in a different account/project from production, ideally with object lock.

Env: MIGRATIONS_DATABASE_URL (owner role), ENV, RELEASE, BACKUP_S3_BUCKET, BACKUP_S3_ENDPOINT_URL (optional),
BACKUP_RETENTION_DAYS (default 35). Needs pg_dump of the server's major version (16) on PATH.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg


def dsn() -> str:
    url = os.environ.get("MIGRATIONS_DATABASE_URL")
    if not url:
        sys.exit("MIGRATIONS_DATABASE_URL (owner role) is required")
    return url.replace("postgresql+psycopg://", "postgresql://")


def table_counts(conn_str: str) -> tuple[str, dict[str, int]]:
    with psycopg.connect(conn_str) as c:
        version = c.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        tables = [r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1")]
        counts = {t: c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables}
    return version, counts


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def s3():
    import boto3
    return boto3.client("s3", endpoint_url=os.environ.get("BACKUP_S3_ENDPOINT_URL") or None)


def main(out_dir: str | None) -> int:
    env = os.environ.get("ENV", "dev")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = f"eco-{env}-{stamp}"
    work = Path(out_dir or tempfile.mkdtemp(prefix="eco-backup-"))
    work.mkdir(parents=True, exist_ok=True)
    dump, manifest_path = work / f"{base}.dump", work / f"{base}.manifest.json"
    t0 = time.time()
    # counts first, then the dump: in a live system rows can only have been added in between, which the drill allows
    version, counts = table_counts(dsn())
    subprocess.run(["pg_dump", "--format=custom", "--compress=6", "--no-password", f"--file={dump}", dsn()],
                   check=True)
    manifest = {"created_at": stamp, "env": env, "release": os.environ.get("RELEASE", "unknown"),
                "schema_version": version, "tables": counts, "dump": dump.name, "sha256": sha256(dump),
                "bytes": dump.stat().st_size, "seconds": round(time.time() - t0, 1)}
    manifest_path.write_text(json.dumps(manifest, indent=1))
    print(f"dumped {sum(counts.values())} rows from {len(counts)} tables, {manifest['bytes']:,} bytes "
          f"in {manifest['seconds']}s (schema {version})")
    bucket = os.environ.get("BACKUP_S3_BUCKET")
    if bucket and not out_dir:
        cli, prefix = s3(), f"{env}/"
        for p in (dump, manifest_path):
            cli.upload_file(str(p), bucket, prefix + p.name, ExtraArgs={"ServerSideEncryption": "AES256"})
        print(f"uploaded to s3://{bucket}/{prefix}{base}.*")
        keep = timedelta(days=int(os.environ.get("BACKUP_RETENTION_DAYS", "35")))
        cutoff = datetime.now(UTC) - keep
        old = [o["Key"] for page in cli.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
               for o in page.get("Contents", []) if o["LastModified"] < cutoff]
        for i in range(0, len(old), 1000):
            cli.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in old[i:i + 1000]]})
        print(f"pruned {len(old)} object(s) older than {keep.days} days")
        for p in (dump, manifest_path):
            p.unlink()
    else:
        print(f"wrote {dump} and {manifest_path}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir")
    sys.exit(main(ap.parse_args().out_dir))
