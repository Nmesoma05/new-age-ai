"""Post-deploy smoke test: verifies the critical functions of a live environment through its public URLs.

    python -m scripts.smoke --web https://staging.example.com --api https://api.staging.example.com --mode staging
    python -m scripts.smoke --web https://app.example.com --api https://api.example.com --mode production

staging    : full journey with a throwaway account (sign up through the web app, create a workspace, one AI
             generation, upload + download a PDF, export my data), then deletes that account.
production : no data is created. Platform checks, plus sign-in/sign-out with a dedicated synthetic account when
             SMOKE_EMAIL and SMOKE_PASSWORD are set.
Both       : health, readiness (database, storage, scanner, schema at head), the expected release, security
             headers and CSP, legal pages (production refuses drafts), API docs hidden, unsigned payment webhook
             refused, CORS closed to other origins.
Exit code 0 only if every check passed. Prints no secrets.
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
import time

import httpx

PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj "
       b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")
CSRF = {"x-eco-csrf": "1"}


class Smoke:
    def __init__(self, web: str, api: str, mode: str, release: str | None):
        self.web, self.api, self.mode, self.release = web.rstrip("/"), api.rstrip("/"), mode, release
        self.results: list[tuple[str, bool, str]] = []
        self.https = self.web.startswith("https://")

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.results.append((name, bool(ok), detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok or not detail else '  -> ' + detail}", flush=True)
        return bool(ok)

    def run(self) -> int:
        with httpx.Client(timeout=30, follow_redirects=False) as c:
            self.platform(c)
        if self.mode == "staging":
            with httpx.Client(base_url=self.web, timeout=60, headers=CSRF) as w:
                self.journey(w)
        elif os.environ.get("SMOKE_EMAIL") and os.environ.get("SMOKE_PASSWORD"):
            with httpx.Client(base_url=self.web, timeout=30, headers=CSRF) as w:
                self.signin_only(w)
        else:
            self.check("synthetic sign-in (set SMOKE_EMAIL/SMOKE_PASSWORD)", True, "skipped: no synthetic account")
        failed = [r for r in self.results if not r[1]]
        print(f"\n{len(self.results) - len(failed)}/{len(self.results)} checks passed")
        return 1 if failed else 0

    # ------------------------------------------------------------------ platform
    def platform(self, c: httpx.Client) -> None:
        h = c.get(f"{self.api}/health")
        self.check("API /health", h.status_code == 200, str(h.status_code))
        if self.release:
            got = h.json().get("release") if h.status_code == 200 else None
            self.check("API runs the expected release", got == self.release, f"got {got}")
        r = None
        for _ in range(12):  # new instances may need a moment to become ready
            r = c.get(f"{self.api}/ready")
            if r.status_code == 200:
                break
            time.sleep(5)
        self.check("API /ready (database, schema, storage, scanner)", r.status_code == 200,
                   r.text[:200] if r is not None else "")
        self.check("API docs hidden", c.get(f"{self.api}/docs").status_code == 404)
        wh = c.post(f"{self.api}/v1/webhooks/paystack", content=b'{"event":"charge.success"}',
                    headers={"content-type": "application/json", "x-paystack-signature": "0" * 128})
        self.check("unsigned payment webhook refused", wh.status_code in (401, 403), str(wh.status_code))
        cors = c.options(f"{self.api}/v1/me", headers={"origin": "https://evil.example", "access-control-request-method": "GET"})
        self.check("CORS closed to other origins", cors.headers.get("access-control-allow-origin") not in ("*", "https://evil.example"))
        page = c.get(f"{self.web}/login")
        self.check("web /login", page.status_code == 200, str(page.status_code))
        csp = page.headers.get("content-security-policy", "")
        self.check("CSP with nonce and no framing", "nonce-" in csp and "frame-ancestors 'none'" in csp)
        self.check("X-Frame-Options / nosniff", page.headers.get("x-frame-options") == "DENY"
                   and page.headers.get("x-content-type-options") == "nosniff")
        if self.https:
            self.check("HSTS", "max-age=" in page.headers.get("strict-transport-security", ""))
            plain = c.get(self.web.replace("https://", "http://", 1) + "/login")
            self.check("http redirects to https", plain.status_code in (301, 302, 307, 308)
                       and plain.headers.get("location", "").startswith("https://"))
        for doc in ("privacy", "terms"):
            d = c.get(f"{self.web}/{doc}")
            ok = d.status_code == 200
            draft = "Draft for legal review" in d.text
            self.check(f"/{doc} published", ok and (self.mode != "production" or not draft),
                       "still a DRAFT" if draft else str(d.status_code))
        if self.mode == "production":
            self.check("robots: staging noindex not leaking into production",
                       "noindex" not in page.headers.get("x-robots-tag", ""))

    # ------------------------------------------------------------------ staging journey
    def journey(self, w: httpx.Client) -> None:
        email = f"smoke+{secrets.token_hex(4)}@example.com"
        pw = secrets.token_urlsafe(18)
        s = w.post("/api/auth/signup", json={"email": email, "password": pw, "display_name": "Smoke Test",
                                             "accept_terms": True})
        if not self.check("sign up through the web app", s.status_code == 200, s.text[:200]):
            return
        try:
            orgs = w.get("/api/proxy/v1/orgs").json()
            w.post(f"/api/proxy/v1/orgs/{orgs[0]['id']}/products", json={"product": "creator"})
            ws = w.post(f"/api/proxy/v1/orgs/{orgs[0]['id']}/workspaces", json={"name": "Smoke", "product": "creator"})
            if not self.check("create a workspace", ws.status_code == 201, ws.text[:200]):
                return
            wid = ws.json()["id"]
            conv = w.post(f"/api/proxy/v1/workspaces/{wid}/conversations", json={}).json()["id"]
            t0 = time.time()
            m = w.post(f"/api/proxy/v1/workspaces/{wid}/conversations/{conv}/messages",
                       json={"content": "Write one short Instagram caption for a Lagos coffee shop's Monday promo."})
            reply = m.json().get("assistant_message", {}).get("content", "") if m.status_code == 201 else ""
            self.check("AI generation (real model)", m.status_code == 201 and len(reply) > 10,
                       f"{m.status_code} in {time.time() - t0:.1f}s {m.text[:150] if m.status_code != 201 else ''}")
            up = w.post(f"/api/proxy/v1/workspaces/{wid}/documents", files={"file": ("smoke.pdf", PDF, "application/pdf")})
            if self.check("upload a PDF (virus scan + storage)", up.status_code == 201, up.text[:200]):
                doc = up.json()
                for _ in range(10):
                    if w.get(f"/api/proxy/v1/workspaces/{wid}/documents/{doc['id']}").json().get("scan_status") == "clean":
                        break
                    time.sleep(2)
                link = w.post(f"/api/proxy/v1/workspaces/{wid}/documents/{doc['id']}/download-url")
                got = w.get("/api/proxy" + httpx.URL(link.json()["url"]).path) if link.status_code == 200 else None
                self.check("download it back", got is not None and got.content == PDF,
                           str(link.status_code if got is None else got.status_code))
            ex = w.get("/api/proxy/v1/me/export")
            self.check("export my data", ex.status_code == 200 and email in ex.text, str(ex.status_code))
        finally:
            d = w.post("/api/proxy/v1/me/delete", json={"password": pw, "confirm": "DELETE"})
            self.check("delete the smoke account", d.status_code == 200, d.text[:200])

    def signin_only(self, w: httpx.Client) -> None:
        r = w.post("/api/auth/login", json={"email": os.environ["SMOKE_EMAIL"], "password": os.environ["SMOKE_PASSWORD"]})
        if self.check("synthetic account signs in", r.status_code == 200, str(r.status_code)):
            self.check("authenticated API call", w.get("/api/proxy/v1/me").status_code == 200)
            w.post("/api/auth/logout")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", required=True)
    ap.add_argument("--api", required=True)
    ap.add_argument("--mode", choices=["staging", "production"], required=True)
    ap.add_argument("--release", default=os.environ.get("EXPECTED_RELEASE"))
    a = ap.parse_args()
    print(f"Smoke test: {a.mode} web={a.web} api={a.api}")
    return Smoke(a.web, a.api, a.mode, a.release).run()


if __name__ == "__main__":
    sys.exit(main())
