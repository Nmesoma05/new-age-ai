"""QA security probes (areas 1, 7, 11, 13). Each test is an attack or abuse case; all run against the real API + DB."""
import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from tests.freelancer.conftest import fgen, fl  # noqa: F401
from tests.helpers import PDF_BYTES


def _b64(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


# ------------------------------------------------------------------ authentication
async def test_forged_and_misused_tokens_rejected(client, signup):
    a = await signup()
    s = get_settings()
    now = datetime.now(UTC)
    good = {"sub": str(a.user_id), "iss": s.jwt_issuer, "iat": now, "nbf": now, "exp": now + timedelta(minutes=5),
            "typ": "access"}
    key = s.jwt_secret.get_secret_value()
    forged = {
        "alg_none": f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64({**good, 'iat': 0, 'nbf': 0, 'exp': 9999999999})}.",
        "wrong_secret": jwt.encode(good, "not-the-secret-" * 4, algorithm="HS256"),
        "expired": jwt.encode({**good, "exp": now - timedelta(seconds=1)}, key, algorithm="HS256"),
        "wrong_issuer": jwt.encode({**good, "iss": "evil"}, key, algorithm="HS256"),
        "wrong_type": jwt.encode({**good, "typ": "refresh"}, key, algorithm="HS256"),
        "no_type": jwt.encode({k: v for k, v in good.items() if k != "typ"}, key, algorithm="HS256"),
        "bad_sub": jwt.encode({**good, "sub": "1 OR 1=1"}, key, algorithm="HS256"),
        "ghost_user": jwt.encode({**good, "sub": str(uuid.uuid4())}, key, algorithm="HS256"),
        "refresh_as_bearer": a.refresh if hasattr(a, "refresh") else "x" * 64,
        "garbage": "a.b.c",
    }
    for name, tok in forged.items():
        r = await client.get("/v1/me", headers={"authorization": f"Bearer {tok}"})
        assert r.status_code == 401, (name, r.status_code)
        assert "Traceback" not in r.text and key not in r.text


async def test_access_token_lifetime_is_short(client, signup):
    a = await signup()
    claims = jwt.decode(next(v for k, v in a.h.items() if k.lower() == "authorization")[7:], options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] <= 15 * 60  # logout can't kill an access token: keep the window short


async def test_mass_assignment_on_profile_is_ignored(client, signup):
    a = await signup("Ada")
    r = await client.patch("/v1/me", headers=a.h, json={"display_name": "Ada O", "email": "boss@example.com",
                                                         "is_active": False, "password_hash": "x", "id": str(uuid.uuid4())})
    assert r.status_code in (200, 422)
    me = (await client.get("/v1/me", headers=a.h)).json()
    assert me["email"] == a.email and me["id"] == str(a.user_id)


async def test_email_is_case_insensitive_and_unique(client, signup):
    a = await signup("Ada")
    r = await client.post("/v1/auth/login", json={"email": a.email.upper(), "password": "correct-horse-battery"})
    assert r.status_code == 200
    dup = await client.post("/v1/auth/signup", json={"email": a.email.upper(), "password": "another-good-pass",
                                                     "display_name": "Clone"})
    assert dup.status_code == 409


async def test_signup_input_limits(client):
    base = {"email": "x@example.com", "password": "correct-horse-battery", "display_name": "X"}
    for bad in ({"password": "short"}, {"password": "p" * 129}, {"display_name": "x" * 10_000}, {"email": "not-an-email"},
                {"email": "a@b.c" + "x" * 400}):
        r = await client.post("/v1/auth/signup", json={**base, **bad})
        assert r.status_code == 422, bad


# ------------------------------------------------------------------ validation and errors
async def test_malformed_requests_get_clean_4xx(client, signup, make_workspace):
    a = await signup()
    ws = await make_workspace(a)
    cases = [
        ("GET", "/v1/workspaces/not-a-uuid", None),
        ("GET", f"/v1/workspaces/{ws}/assets?limit=100000", None),
        ("GET", f"/v1/workspaces/{ws}/assets?limit=-1", None),
        ("GET", f"/v1/workspaces/{ws}/documents?cursor='; DROP TABLE assets;--", None),
        ("POST", f"/v1/workspaces/{ws}/projects", {"name": None}),
        ("POST", f"/v1/workspaces/{ws}/projects", {"name": "x" * 100_000}),
        ("POST", f"/v1/workspaces/{ws}/projects", [1, 2, 3]),
    ]
    for method, url, body in cases:
        r = await client.request(method, url, headers=a.h, json=body)
        assert 400 <= r.status_code < 500, (url, r.status_code, r.text[:200])
        assert "Traceback" not in r.text and "sqlalchemy" not in r.text.lower()
    raw = await client.post(f"/v1/workspaces/{ws}/projects", headers={**a.h, "content-type": "application/json"},
                            content=b'{"name": "unterminated')
    assert raw.status_code == 422 and raw.headers["content-type"].startswith("application/problem+json")


async def test_injection_strings_are_data(client, signup, make_workspace):
    a = await signup()
    ws = await make_workspace(a)
    evil = ["'; DROP TABLE users; --", "\" OR \"1\"=\"1", "{{7*7}}", "${7*7}", "<script>alert(1)</script>",
            "Ọlá Chịamaka 🚀 مرحبا", "‮gnp.exe", "%00", "../../etc/passwd"]
    for s in evil:
        r = await client.post(f"/v1/workspaces/{ws}/projects", headers=a.h, json={"name": s[:120]})
        assert r.status_code == 201, (s, r.text)
        assert r.json()["name"] == s[:120]  # stored verbatim, not evaluated
    listed = (await client.get(f"/v1/workspaces/{ws}/projects", headers=a.h)).json()
    names = [p["name"] for p in (listed["data"] if isinstance(listed, dict) else listed)]
    assert len(names) >= len(evil)


# ------------------------------------------------------------------ files
async def test_unicode_filename_upload_and_download(client, signup, make_workspace):
    """Nigerian names are common in CV filenames ("Chịamaka Ọkafọ CV.pdf"): must not crash the download."""
    a = await signup()
    ws = await make_workspace(a)
    r = await client.post(f"/v1/workspaces/{ws}/documents", headers=a.h,
                          files={"file": ("Chịamaka Ọkafọ CV “final”.pdf", PDF_BYTES, "application/pdf")})
    assert r.status_code == 201, r.text
    doc = r.json()["id"]
    link = await client.post(f"/v1/workspaces/{ws}/documents/{doc}/download-url", headers=a.h)
    if link.status_code == 409:  # scanner still pending in this environment
        pytest.skip("file scan pending")
    path = "/" + link.json()["url"].split("/", 3)[3]
    dl = await client.get(path)
    assert dl.status_code == 200 and dl.content == PDF_BYTES
    cd = dl.headers["content-disposition"]
    assert cd.startswith("attachment") and "filename*=UTF-8''Ch%E1%BB%8Bamaka" in cd


async def test_unicode_titles_export(client, fl, fgen):  # noqa: F811
    a, ws = await fl()
    cv = (await fgen(a, ws, tool="cv", target_role="Designer", market="us")).json()["run"]
    asset = (await client.post(f"/v1/workspaces/{ws}/freelancer/runs/{cv['id']}/save", headers=a.h,
                               json={"title": "CV for Ọ̀bá Chịamaka"})).json()["id"]
    for fmt in ("md", "txt", "html"):
        r = await client.get(f"/v1/workspaces/{ws}/freelancer/work/{asset}/export?format={fmt}", headers=a.h)
        assert r.status_code == 200, (fmt, r.text[:200])
        assert "filename*=UTF-8''" in r.headers["content-disposition"]


async def test_html_upload_is_never_served_as_html(client, signup, make_workspace):
    a = await signup()
    ws = await make_workspace(a)
    r = await client.post(f"/v1/workspaces/{ws}/documents", headers=a.h,
                          files={"file": ("cv.html", b"<html><script>alert(document.cookie)</script></html>", "text/html")})
    assert r.status_code == 201 and r.json()["content_type"] == "text/plain"
    link = await client.post(f"/v1/workspaces/{ws}/documents/{r.json()['id']}/download-url", headers=a.h)
    if link.status_code == 409:
        pytest.skip("file scan pending")
    dl = await client.get("/" + link.json()["url"].split("/", 3)[3])
    assert dl.headers["content-type"].startswith("text/plain")
    assert "sandbox" in dl.headers["content-security-policy"] and dl.headers["x-content-type-options"] == "nosniff"


async def test_download_tokens_cannot_be_forged_or_swapped(client, signup, make_workspace):
    a = await signup()
    await make_workspace(a)
    for tok in ("x", "a.b.c", jwt.encode({"k": "../../etc/passwd", "f": "p", "t": "text/plain",
                                           "exp": datetime.now(UTC) + timedelta(minutes=5)}, "guess", algorithm="HS256")):
        r = await client.get(f"/v1/files/{tok}")
        assert r.status_code in (401, 403, 404), r.status_code


# ------------------------------------------------------------------ exports
async def test_calendar_exports_neutralise_formulas_and_header_injection(client, signup):
    a = await signup("Ada", product=None)
    on = await client.post("/v1/creator/onboarding", headers=a.h, json={"mode": "solo", "client": {
        "client_name": "Kola", "platforms": ["instagram"]}})
    assert on.status_code == 201, on.text
    ws = on.json()["workspace_id"]
    for title in ('=HYPERLINK("http://evil.example","Click")', "+SUM(1,2)", "@cmd", "Line one\r\nATTENDEE:mailto:x@evil.example"):
        r = await client.post(f"/v1/workspaces/{ws}/creator/calendar", headers=a.h, json={
            "title": title, "platform": "instagram", "scheduled_for": "2026-12-03T09:00:00Z"})
        assert r.status_code == 201, r.text
    csv_ = await client.get(f"/v1/workspaces/{ws}/creator/calendar/export?format=csv&start=2026-12-01&end=2026-12-31",
                            headers=a.h)
    assert csv_.status_code == 200
    for line in csv_.text.splitlines()[1:]:
        assert not line.startswith(("=", "+", "@", '"=', '"+', '"@')), line
    ics = await client.get(f"/v1/workspaces/{ws}/creator/calendar/export?format=ics&start=2026-12-01&end=2026-12-31",
                           headers=a.h)
    assert not any(line.startswith("ATTENDEE") for line in ics.text.splitlines()), "ICS header injection"
    assert "\r" not in ics.text.replace("\r\n", ""), "bare CR inside an ICS line"


async def test_html_export_escapes_user_content(client, fl, fgen):  # noqa: F811
    a, ws = await fl()
    cv = (await fgen(a, ws, tool="cv", target_role="Designer", market="us")).json()["run"]
    title = '<img src=x onerror="alert(document.cookie)">'
    asset = (await client.post(f"/v1/workspaces/{ws}/freelancer/runs/{cv['id']}/save", headers=a.h,
                               json={"title": title})).json()["id"]
    html = await client.get(f"/v1/workspaces/{ws}/freelancer/work/{asset}/export?format=html", headers=a.h)
    assert html.status_code == 200 and "<img" not in html.text and "&lt;img" in html.text
    assert "attachment" in html.headers["content-disposition"]
    import re
    m = re.fullmatch(r'attachment; filename="([^"\\]*)"; filename\*=UTF-8\'\'([A-Za-z0-9%._~-]*)', html.headers["content-disposition"])
    assert m, html.headers["content-disposition"]  # no quote/backslash can break out of either parameter


# ------------------------------------------------------------------ CORS
async def test_cors_only_for_configured_origins(client):
    bad = await client.options("/v1/me", headers={"origin": "https://evil.example", "access-control-request-method": "GET"})
    assert bad.headers.get("access-control-allow-origin") != "https://evil.example"
    assert bad.headers.get("access-control-allow-origin") != "*"
