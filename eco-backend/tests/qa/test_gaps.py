"""QA gap tests (areas 9, 11, 13): seats, past-due grace, oversized/hostile bodies, leak-free errors, headers."""

import pytest


async def test_seat_limit_on_pro(client, signup, activate_plan):
    owner = await signup("Owner")
    org = (await client.post("/v1/orgs", headers=owner.h, json={"name": "Agency"})).json()["id"]
    await activate_plan(org, "pro")  # 3 seats incl. the owner
    for n in ("Ann", "Ben"):
        m = await signup(n)
        r = await client.post(f"/v1/orgs/{org}/members", headers=owner.h, json={"email": m.email, "role": "member"})
        assert r.status_code == 201, r.text
    extra = await signup("Cy")
    r = await client.post(f"/v1/orgs/{org}/members", headers=owner.h, json={"email": extra.email, "role": "member"})
    assert r.status_code == 402 and r.json()["code"] == "seat_limit_reached" and "3 seat" in r.json()["detail"]


async def test_past_due_keeps_access_inside_grace_only(client, signup, activate_plan, owner_db):
    a = await signup()
    await activate_plan(a.org_id, "pro")
    with owner_db.cursor() as c:
        c.execute("UPDATE subscriptions SET status='past_due', period_start=now()-interval '31 days', period_end=now()-interval '1 day', "
                  "grace_until=now()+interval '2 days' WHERE org_id=%s", (str(a.org_id),))
    sub = (await client.get(f"/v1/orgs/{a.org_id}/subscription", headers=a.h)).json()
    assert sub["ai_unlimited"] is True
    with owner_db.cursor() as c:
        c.execute("UPDATE subscriptions SET grace_until=now()-interval '1 hour' WHERE org_id=%s", (str(a.org_id),))
    sub = (await client.get(f"/v1/orgs/{a.org_id}/subscription", headers=a.h)).json()
    assert sub["ai_unlimited"] is False
    usage = (await client.get(f"/v1/orgs/{a.org_id}/usage", headers=a.h)).json()
    assert usage["free_remaining"] is not None  # back on Free limits, nothing deleted


@pytest.mark.parametrize("size_mb", [3, 25])
async def test_oversized_json_body_is_refused_cleanly(client, signup, size_mb):
    a = await signup()
    blob = "x" * (size_mb * 1024 * 1024)
    r = await client.patch("/v1/me", headers=a.h, json={"display_name": blob})
    assert r.status_code in (413, 422), r.status_code
    assert blob[:1000] not in r.text  # the input isn't echoed back


async def test_deeply_nested_json_does_not_crash(client, signup, make_workspace):
    a = await signup()
    await make_workspace(a)
    body = "[" * 50000 + "]" * 50000
    r = await client.post("/v1/auth/login", content=body, headers={"content-type": "application/json"})
    assert 400 <= r.status_code < 500


async def test_errors_leak_no_internals(client, signup):
    a = await signup()
    probes = [
        client.get("/v1/workspaces/not-a-uuid", headers=a.h),
        client.post("/v1/auth/login", content=b"{bad json", headers={"content-type": "application/json"}),
        client.get("/v1/orgs/00000000-0000-0000-0000-000000000000/usage", headers=a.h),
        client.post("/v1/auth/login", json={"email": "' OR 1=1 --", "password": "x" * 12}),
    ]
    for r in [await p for p in probes]:
        assert 400 <= r.status_code < 500, (r.status_code, r.text[:200])
        low = r.text.lower()
        for leak in ("traceback", "sqlalchemy", "psycopg", "select ", "/home/", "file \"", "postgres"):
            assert leak not in low, (leak, r.text[:300])
        assert r.headers["content-type"].startswith("application/problem+json") or "json" in r.headers["content-type"]
        assert r.headers.get("x-request-id")


async def test_api_security_headers(client, signup):
    a = await signup()
    r = await client.get("/v1/me", headers=a.h)
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert "server" not in {k.lower() for k in r.headers} or "uvicorn" not in r.headers.get("server", "").lower()
    assert "no-store" in r.headers.get("cache-control", ""), r.headers  # personal data must not be cached


# Static reference data only (constants; no user, org or workspace data). A new public route fails this test.
EXPECTED_OPEN = ["GET /v1/business/capabilities", "GET /v1/business/categories", "GET /v1/creator/capabilities",
                 "GET /v1/freelancer/capabilities", "GET /v1/freelancer/reference"]


async def test_unauthenticated_everywhere(client):
    """Every /v1 route except the public ones must refuse a request with no token."""
    from app.main import create_app
    public = {"/v1/auth/signup", "/v1/auth/login", "/v1/auth/refresh", "/v1/auth/logout", "/v1/webhooks/paystack",
              "/v1/auth/password/forgot", "/v1/auth/password/reset", "/v1/files/{token}"}
    public_prefixes = ("/v1/review/",)  # client review links: capability URL with its own token
    checked, open_routes = 0, []
    for route in create_app().routes:
        p = getattr(route, "path", "")
        if not p.startswith("/v1") or p in public or p.startswith(public_prefixes):
            continue
        url = p.replace("{", "").replace("}", "")
        for m in sorted(getattr(route, "methods", []) or []):
            if m == "HEAD":
                continue
            r = await client.request(m, url.replace("workspace_id", "00000000-0000-0000-0000-000000000000"), json={})
            if r.status_code < 400:
                open_routes.append(f"{m} {p}")
            checked += 1
    assert checked > 150
    assert sorted(open_routes) == sorted(EXPECTED_OPEN), sorted(open_routes)


# ---------------------------------------------------------------- client IP + per-IP limits (BUG-10, BUG-11)
class _Req:
    def __init__(self, peer, xff=None):
        self.client = type("C", (), {"host": peer})()
        self.headers = {"x-forwarded-for": xff} if xff else {}


def test_client_ip_resolution():
    from app.core.clientip import client_ip
    assert client_ip(_Req("198.51.100.7")) == "198.51.100.7"                       # direct, untrusted peer
    assert client_ip(_Req("198.51.100.7", "1.2.3.4")) == "198.51.100.7"            # untrusted peer can't claim an IP
    assert client_ip(_Req("127.0.0.1", "203.0.113.5")) == "203.0.113.5"            # via our web server
    assert client_ip(_Req("127.0.0.1", "6.6.6.6, 203.0.113.5")) == "203.0.113.5"   # spoofed left entries ignored
    assert client_ip(_Req("127.0.0.1")) is None                                     # unknown, not 127.0.0.1
    assert client_ip(_Req("127.0.0.1", "not-an-ip")) is None


def _from(ip):
    return {"x-forwarded-for": ip}


async def test_failed_signins_limited_per_ip(client, signup, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "login_ip_max_failures", 3)
    victims = [await signup(f"V{i}") for i in range(4)]
    for v in victims[:3]:  # one wrong guess each: the per-account lockout never triggers
        r = await client.post("/v1/auth/login", headers=_from("203.0.113.5"), json={"email": v.email, "password": "wrong-guess-1"})
        assert r.status_code == 401
    r = await client.post("/v1/auth/login", headers=_from("203.0.113.5"),
                          json={"email": victims[3].email, "password": "correct-horse-battery"})
    assert r.status_code == 429 and r.json()["code"] == "rate_limited" and int(r.headers["retry-after"]) > 0
    ok = await client.post("/v1/auth/login", headers=_from("198.51.100.9"),
                           json={"email": victims[3].email, "password": "correct-horse-battery"})
    assert ok.status_code == 200  # a different network is unaffected
    # successful sign-ins never count
    for _ in range(5):
        assert (await client.post("/v1/auth/login", headers=_from("198.51.100.9"),
                                  json={"email": victims[3].email, "password": "correct-horse-battery"})).status_code == 200


async def test_signups_limited_per_ip(client, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "signup_ip_per_hour", 2)
    codes = []
    for i in range(3):
        r = await client.post("/v1/auth/signup", headers=_from("203.0.113.8"),
                              json={"email": f"bulk{i}@example.com", "password": "correct-horse-battery", "display_name": "B"})
        codes.append(r.status_code)
    assert codes == [201, 201, 429]


async def test_forgot_limited_per_ip(client, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "forgot_ip_per_hour", 2)
    codes = [(await client.post("/v1/auth/password/forgot", headers=_from("203.0.113.9"),
                                json={"email": f"x{i}@example.com"})).status_code for i in range(3)]
    assert codes[-1] == 429 and codes[0] != 429


async def test_audit_records_the_person_not_our_server(client, signup, owner_db):
    a = await signup()
    await client.post("/v1/auth/login", headers={**_from("203.0.113.44"), "user-agent": "Mozilla/5.0 (Phone)"},
                      json={"email": a.email, "password": "correct-horse-battery"})
    with owner_db.cursor() as c:
        c.execute("SELECT host(ip), user_agent FROM audit_events WHERE action='auth.login' ORDER BY id DESC LIMIT 1")
        assert c.fetchone() == ("203.0.113.44", "Mozilla/5.0 (Phone)")
        c.execute("SELECT count(*) FROM audit_events WHERE host(ip)='127.0.0.1'")
        assert c.fetchone()[0] == 0


# ---------------------------------------------------------------- concurrency: Free limit can't be overrun
async def test_free_limit_holds_under_concurrent_requests(client, signup, make_workspace, owner_db):
    import asyncio
    a = await signup("Racer")
    ws = await make_workspace(a)
    convs = [(await client.post(f"/v1/workspaces/{ws}/conversations", headers=a.h, json={})).json()["id"] for _ in range(6)]
    owner_db.execute("INSERT INTO usage_counters VALUES (%s, date_trunc('month', now())::date, 29)", (a.org_id,))
    rs = await asyncio.gather(*[client.post(f"/v1/workspaces/{ws}/conversations/{c}/messages", headers=a.h,
                                            json={"content": "Write a post"}) for c in convs])
    codes = sorted(r.status_code for r in rs)
    used = owner_db.execute("SELECT free_generations_used FROM usage_counters WHERE org_id=%s", (a.org_id,)).fetchone()[0]
    assert codes.count(201) == 1 and codes.count(402) == 5, codes
    assert used == 30
