"""Cross-tenant sweep over EVERY /v1 route (QA, area 8 + 13).

Run against the e2e server after the browser suites have filled `eco_e2e` with other people's data:
    python -m tests.qa.idor_sweep [--api http://127.0.0.1:8000]

It signs up three fresh "attacker" accounts (one per division), then calls every route/method with the path
filled two ways:
  A. every id = a victim's id                     (someone else's workspace and object)
  B. workspace/org = the attacker's own, object ids = a victim's   (classic IDOR through your own workspace)
Bodies are `{}` (mutations mostly stop at validation; that's recorded separately so coverage isn't overstated).

PASS: 401/403/404/405/409/422 and the body doesn't contain the victim id we didn't send ourselves.
FAIL: any 2xx/3xx (access to someone else's data), any 5xx (crash), or a victim id echoed back.
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
import uuid
from collections import Counter

import httpx
import psycopg

DSN = "postgresql://eco_owner:owner_dev_pw@localhost/eco_e2e"
TABLE = {"org_id": "organisations", "user_id": "users", "team_id": "teams", "workspace_id": "workspaces",
         "project_id": "projects", "document_id": "documents", "conversation_id": "conversations",
         "asset_id": "assets", "run_id": "agent_runs", "action_id": "pending_actions", "memory_id": "memory_items",
         "campaign_id": "campaigns", "link_id": "review_links", "metric_id": "post_metrics",
         "result_id": "marketing_results", "opp_id": "opportunities", "app_id": "applications",
         "sid": "interview_sessions", "integration_id": "integrations",
         "item_id": "calendar_items"}
SKIP_PUBLIC = ("/v1/review/{token}", "/v1/files/{token}")  # token-addressed by design; tested separately


def victim_ids(exclude_users: set[str], own_orgs: set[str]) -> dict[str, list[str]]:
    """Newest rows that belong to someone else (never the attackers' own users/orgs/workspaces)."""
    out: dict[str, list[str]] = {}
    with psycopg.connect(DSN) as c:
        for p, t in TABLE.items():
            if t == "users":
                q, args = "SELECT id::text FROM users WHERE NOT (id::text = ANY(%s))", (list(exclude_users),)
            elif t == "organisations":
                q, args = "SELECT id::text FROM organisations WHERE NOT (id::text = ANY(%s))", (list(own_orgs),)
            else:
                has_org = c.execute("SELECT 1 FROM information_schema.columns WHERE table_name=%s AND "
                                    "column_name='org_id'", (t,)).fetchone()
                q = (f"SELECT id::text FROM {t} WHERE NOT (org_id::text = ANY(%s))" if has_org
                     else f"SELECT id::text FROM {t} WHERE %s IS NOT NULL")
                args = (list(own_orgs),)
            ids = [r[0] for r in c.execute(q + " ORDER BY created_at DESC LIMIT 3", args).fetchall()]
            out[p] = ids or [str(uuid.uuid4())]  # no victim rows: random id (still checks for crashes)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    a = ap.parse_args()
    api = httpx.Client(base_url=a.api, timeout=30)
    spec = api.get("/openapi.json").json()

    attackers = {}
    for product in ("creator", "business", "freelancer"):
        email = f"attacker-{product}-{uuid.uuid4().hex[:6]}@example.com"
        r = api.post("/v1/auth/signup", json={"email": email, "password": "attacker-pass-123", "display_name": "Mallory",
                                              "product": product})
        r.raise_for_status()
        b = r.json()
        h = {"authorization": f"Bearer {b['tokens']['access_token']}"}
        org = b["personal_org_id"]
        if product == "freelancer":
            from tests.freelancer.helpers import PROFILE
            ws = api.post("/v1/freelancer/onboarding", headers=h, json={"profile": PROFILE}).json()["workspace_id"]
        else:
            ws = api.post(f"/v1/orgs/{org}/workspaces", headers=h, json={"name": "Mine", "product": product}).json()["id"]
        attackers[product] = {"h": h, "org": org, "ws": ws, "user": b["user"]["id"]}
    mine = {v["user"] for v in attackers.values()}
    with psycopg.connect(DSN) as c:
        own_orgs = {v["org"] for v in attackers.values()} | {r[0] for r in c.execute("SELECT org_id::text FROM org_members WHERE user_id::text = ANY(%s)",
                                            (list(mine),)).fetchall()}
        own_ws = {r[0] for r in c.execute("SELECT id::text FROM workspaces WHERE org_id::text = ANY(%s)",
                                          (list(own_orgs),)).fetchall()}
    vic = victim_ids(mine, own_orgs)
    assert not set(vic["workspace_id"]) & own_ws and not set(vic["org_id"]) & own_orgs
    vic["key"] = ["youtube"]

    results, counts = [], Counter()
    for path, ops in spec["paths"].items():
        params = re.findall(r"{(\w+)}", path)
        if not path.startswith("/v1") or not params or path.startswith(SKIP_PUBLIC):
            continue
        for method in ops:
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            for mode, (prod, att) in itertools.product("AB", attackers.items()):
                scope = {"workspace_id", "org_id", "key"}  # 'key' names a provider, not someone's object
                if mode == "B" and (not scope & set(params) or not set(params) - scope):
                    continue  # B needs your own scope AND someone else's object; otherwise it's legitimately yours
                fill = {}
                for p in params:
                    if mode == "B" and p == "workspace_id":
                        fill[p] = att["ws"]
                    elif mode == "B" and p == "org_id":
                        fill[p] = att["org"]
                    else:
                        fill[p] = vic[p][0]
                url = path.format(**fill)
                r = api.request(method.upper(), url, headers=att["h"],
                                json={} if method in ("post", "put", "patch") else None)
                sent = set(fill.values())
                leaked = [i for p in params for i in vic.get(p, []) if i not in sent and i in r.text]
                if r.status_code >= 500:
                    verdict = "FAIL-crash"
                elif r.status_code < 400:
                    verdict = "FAIL-access"
                elif leaked:
                    verdict = "FAIL-leak"
                elif r.status_code == 422:
                    verdict = "pass-validation"  # stopped before data access could be exercised
                else:
                    verdict = "pass"
                counts[verdict] += 1
                if verdict.startswith("FAIL"):
                    results.append({"verdict": verdict, "mode": mode, "as": prod, "method": method.upper(),
                                    "url": url, "status": r.status_code, "body": r.text[:200]})
    print(json.dumps({"counts": counts, "failures": results}, indent=1))
    return 1 if results else 0


if __name__ == "__main__":
    sys.exit(main())
