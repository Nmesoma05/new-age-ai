"""Release gate: refuse migrations that would break the running release or make rollback unsafe.

    python -m scripts.migration_safety --since 0008_account_recovery     # production's current revision
    python -m scripts.migration_safety --since none                      # first deploy, empty database

Deploys run migrations BEFORE the new code starts, while the old code still serves traffic, and a rollback runs the
old code against the new schema. So every migration must be additive ("expand"): new tables, new nullable columns,
new indexes. Removing or renaming things ("contract") ships in a later release, once no running code uses them.
This scans the upgrade() of every migration after --since for destructive statements and exits 1 if any are found,
unless ALLOW_DESTRUCTIVE_MIGRATION=<revision> names that exact revision (set by the approver for one release).
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from pathlib import Path

DESTRUCTIVE = [r"\bDROP\s+(TABLE|COLUMN|INDEX|TYPE|SCHEMA|POLICY|FUNCTION|TRIGGER|VIEW)\b", r"\bRENAME\b",
               r"\bALTER\s+COLUMN\s+\w+\s+(SET\s+DATA\s+)?TYPE\b", r"\bSET\s+NOT\s+NULL\b", r"\bTRUNCATE\s+(?!ON\b)",
               r"\bDELETE\s+FROM\b", r"\bREVOKE\s+(?!TRUNCATE\s+ON\b)", r"op\.drop_", r"op\.alter_column"]
VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def chain() -> list[tuple[str, str | None, Path]]:
    out = []
    for p in sorted(VERSIONS.glob("*.py")):
        tree = ast.parse(p.read_text())
        vals = {t.id: n.value.value for n in tree.body if isinstance(n, ast.Assign)
                for t in n.targets if isinstance(t, ast.Name) and isinstance(n.value, ast.Constant)}
        out.append((vals["revision"], vals.get("down_revision"), p))
    return out


def upgrade_source(path: Path) -> str:
    """Only upgrade() and the module-level SQL it uses; downgrade() is allowed to drop things."""
    src = path.read_text()
    tree = ast.parse(src)
    parts = [ast.get_source_segment(src, n) for n in tree.body
             if not (isinstance(n, ast.FunctionDef) and n.name == "downgrade")]
    return "\n".join(p for p in parts if p)


def main(since: str) -> int:
    if since == "none":
        print("fresh database (first deploy): every migration applies; no running release to protect")
        return 0
    revs = {r: (down, p) for r, down, p in chain()}
    heads = set(revs) - {d for d, _ in revs.values()}
    if len(heads) != 1:
        print(f"FAIL: migrations must have exactly one head, found {sorted(heads)}")
        return 1
    if since not in revs:
        print(f"FAIL: unknown revision {since!r}")
        return 1
    pending, cur = [], heads.pop()
    while cur and cur != since:
        pending.append(cur)
        cur = revs[cur][0]
    allowed = os.environ.get("ALLOW_DESTRUCTIVE_MIGRATION", "")
    bad = 0
    for rev in reversed(pending):
        src = upgrade_source(revs[rev][1])
        hits = sorted({m.group(0).strip() for pat in DESTRUCTIVE for m in re.finditer(pat, src, re.I)})
        if hits and rev != allowed:
            bad += 1
            print(f"FAIL {rev}: destructive statements in upgrade(): {', '.join(hits)}")
        else:
            print(f"ok   {rev}{' (destructive, approved)' if hits else ''}")
    print(f"{len(pending)} migration(s) to apply after {since}")
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    sys.exit(main(ap.parse_args().since))
