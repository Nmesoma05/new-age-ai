"""Small load test (QA area 12). Run against the e2e server: python -m tests.qa.load [users] [requests_each]

Signs up N users (each with a Creator workspace) and has them hit read endpoints concurrently. Reports
throughput, p50/p95/p99 latency and any non-2xx. One uvicorn worker on a laptop-class container: a baseline,
not a capacity figure.
"""
import asyncio
import statistics
import sys
import time
import uuid

import httpx

API = "http://127.0.0.1:8000"


async def user(c: httpx.AsyncClient, i: int):
    em = f"load-{uuid.uuid4().hex[:8]}@example.com"
    r = await c.post("/v1/auth/signup", json={"email": em, "password": "correct-horse-battery", "display_name": f"L{i}",
                                              "product": "creator"})
    r.raise_for_status()
    h = {"authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    org = r.json()["personal_org_id"]
    ws = (await c.post(f"/v1/orgs/{org}/workspaces", headers=h, json={"name": f"W{i}", "product": "creator"})).json()["id"]
    return h, org, ws


async def main(n: int, each: int):
    async with httpx.AsyncClient(base_url=API, timeout=30) as c:
        users = await asyncio.gather(*[user(c, i) for i in range(n)])
        lat, bad = [], {}

        async def worker(h, org, ws):
            paths = ["/v1/me", f"/v1/workspaces/{ws}", f"/v1/orgs/{org}/usage", f"/v1/workspaces/{ws}/assets",
                     "/v1/creator/clients", f"/v1/workspaces/{ws}/creator/overview"]
            for k in range(each):
                p = paths[k % len(paths)]
                t0 = time.perf_counter()
                r = await c.get(p, headers=h)
                lat.append((time.perf_counter() - t0) * 1000)
                if r.status_code >= 400:
                    bad[f"{r.status_code} {p.split('/')[-1]}"] = bad.get(f"{r.status_code} {p.split('/')[-1]}", 0) + 1
        t0 = time.perf_counter()
        await asyncio.gather(*[worker(*u) for u in users])
        dur = time.perf_counter() - t0
    q = statistics.quantiles(lat, n=100)
    print(f"users={n} requests={len(lat)} duration={dur:.1f}s throughput={len(lat)/dur:.0f} req/s "
          f"p50={q[49]:.0f}ms p95={q[94]:.0f}ms p99={q[98]:.0f}ms max={max(lat):.0f}ms errors={bad or 0}")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 50, int(sys.argv[2]) if len(sys.argv) > 2 else 20))
