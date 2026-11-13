"""A fake set of provider endpoints behind httpx.MockTransport. Nothing here reaches the internet.

The fakes behave like the real APIs in the ways our code depends on (PKCE check, token/refresh/revoke shapes,
YouTube response shapes, Remotive and ExchangeRate-API JSON). They were written from the providers' documentation;
they are NOT a substitute for the live checks listed in docs/INTEGRATIONS.md.
"""
import base64
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.integrations import http as ihttp


class Fake:
    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.challenges: dict[str, str] = {}   # code -> code_challenge the "user" approved
        self.token_scope = ("https://www.googleapis.com/auth/youtube.readonly "
                            "https://www.googleapis.com/auth/yt-analytics.readonly")
        self.refresh_mode = "ok"               # ok | invalid_grant | down
        self.revoke_mode = "ok"
        self.channel_id = "UC_test_channel"
        self.n = 0
        self.overrides: dict[tuple[str, str], object] = {}

    def approve(self, authorize_url: str) -> tuple[str, str]:
        """Pretend the user clicked Allow on Google's page. Returns (state, code)."""
        q = parse_qs(urlsplit(authorize_url).query)
        assert q["code_challenge_method"] == ["S256"]
        self.n += 1
        code = f"code-{self.n}"
        self.challenges[code] = q["code_challenge"][0]
        return q["state"][0], code

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        key = (req.url.host, req.url.path)
        if key in self.overrides:
            o = self.overrides[key]
            return o(req) if callable(o) else o
        form = {k: v[0] for k, v in parse_qs(req.content.decode()).items()} if req.method == "POST" else {}
        if key == ("oauth2.googleapis.com", "/token"):
            if form.get("grant_type") == "authorization_code":
                want = self.challenges.pop(form.get("code", ""), None)
                got = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).rstrip(b"=").decode()
                if want is None or want != got:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return httpx.Response(200, json={"access_token": f"ya29.access-{self.n}", "expires_in": 3599,
                                                 "refresh_token": f"1//refresh-{self.n}", "scope": self.token_scope,
                                                 "token_type": "Bearer"})
            if form.get("grant_type") == "refresh_token":
                if self.refresh_mode == "invalid_grant":
                    return httpx.Response(400, json={"error": "invalid_grant"})
                if self.refresh_mode == "down":
                    return httpx.Response(503)
                self.n += 1
                return httpx.Response(200, json={"access_token": f"ya29.refreshed-{self.n}", "expires_in": 3599})
        if key == ("oauth2.googleapis.com", "/revoke"):
            return httpx.Response(200) if self.revoke_mode == "ok" else httpx.Response(500)
        if key == ("www.googleapis.com", "/youtube/v3/channels"):
            assert req.headers["authorization"].startswith("Bearer ya29.")
            return httpx.Response(200, json={"items": [{"id": self.channel_id, "snippet": {"title": "Ada Cooks"},
                                                        "statistics": {"subscriberCount": "1520",
                                                                       "hiddenSubscriberCount": False}}]})
        if key == ("youtubeanalytics.googleapis.com", "/v2/reports"):
            q = parse_qs(req.url.query.decode())
            assert q["ids"] == ["channel==MINE"] and q["dimensions"] == ["video"]
            return httpx.Response(200, json={
                "columnHeaders": [{"name": n} for n in ("video", "views", "likes", "comments", "shares")],
                "rows": [["vid1", 1200, 80, 12, 5], ["vid2", 300, 10, 1, 0]]})
        if key == ("www.googleapis.com", "/youtube/v3/videos"):
            return httpx.Response(200, json={"items": [
                {"id": "vid1", "snippet": {"title": "Jollof in 10 minutes", "publishedAt": "2026-10-20T10:00:00Z"}},
                {"id": "vid2", "snippet": {"title": "Market day", "publishedAt": "2026-10-28T10:00:00Z"}}]})
        if req.url.host == "open.er-api.com":
            return httpx.Response(200, json={"result": "success", "base_code": "USD",
                                             "time_last_update_utc": "Thu, 12 Nov 2026 00:02:31 +0000",
                                             "time_next_update_utc": "Fri, 13 Nov 2026 00:02:31 +0000",
                                             "rates": {"USD": 1, "NGN": 1500.5, "KES": 129.2, "EUR": 0.92}})
        if key == ("remotive.com", "/api/remote-jobs"):
            return httpx.Response(200, json={"job-count": 3, "jobs": [
                {"id": 101, "url": "https://remotive.com/remote-jobs/design/product-designer-101",
                 "title": "Product Designer", "company_name": "PayCo", "category": "Design", "job_type": "full_time",
                 "publication_date": "2026-11-10T09:00:00", "candidate_required_location": "Europe, Africa",
                 "salary": "$50k - $70k", "description": "<p>Figma &amp; <b>fintech</b></p><script>x()</script>"},
                {"id": 102, "url": "https://remotive.com/remote-jobs/dev/backend-102", "title": "Backend Engineer",
                 "company_name": "Shopa", "category": "Software Development", "job_type": "contract",
                 "publication_date": "2026-11-09T09:00:00", "candidate_required_location": "USA Only",
                 "salary": "", "description": "<p>Python</p>"},
                {"id": 103, "url": "https://evil.example/apply", "title": "Not Remotive", "company_name": "X",
                 "category": "Design", "job_type": "full_time", "publication_date": "",
                 "candidate_required_location": "Worldwide", "salary": "", "description": ""}]})
        return httpx.Response(404, json={"error": "not faked"})

    def count(self, host: str, path: str | None = None) -> int:
        return sum(1 for c in self.calls if c.url.host == host and (path is None or c.url.path == path))


@pytest.fixture
def fake(monkeypatch):
    f = Fake()
    ihttp.set_transport(httpx.MockTransport(f.handler))
    s = get_settings()
    monkeypatch.setattr(s, "google_oauth_client_id", "test-client.apps.googleusercontent.com")
    monkeypatch.setattr(s, "google_oauth_client_secret", SecretStr("test-secret"))
    monkeypatch.setattr(s, "outbound_http_enabled", True)

    async def no_sleep(_s=0, *a, **k):
        f.slept = getattr(f, "slept", []) + [_s]
    monkeypatch.setattr(ihttp, "_sleep", no_sleep)
    yield f
    ihttp.set_transport(None)


@pytest.fixture
def connect_youtube(client, fake):
    async def _c(acct, ws):
        r = await client.post(f"/v1/workspaces/{ws}/integrations/youtube/connect", headers=acct.h,
                              json={"return_to": f"/c/{ws}/settings"})
        assert r.status_code == 200, r.text
        state, code = fake.approve(r.json()["authorization_url"])
        r = await client.post("/v1/integrations/oauth/complete", headers=acct.h, json={"state": state, "code": code})
        assert r.status_code == 200, r.text
        return r.json()["connection"]
    return _c


def body_of(req: httpx.Request) -> str:
    return req.content.decode() if req.content else json.dumps({})
