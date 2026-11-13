// Same-origin proxy to the API. Adds the bearer token from the httpOnly cookie, refreshes it once on 401, and
// passes through only the headers the app needs. Only /v1/* API paths can be reached through it.
import { NextRequest, NextResponse } from "next/server";
import { ACCESS, API_URL, REFRESH, Tokens, clearTokens, clientHeaders, csrfOk, problem, refresh, setTokens } from "@/lib/server";

const MAX_BODY = 21 * 1024 * 1024;
const PASS_RESPONSE = ["content-type", "content-disposition", "retry-after", "x-request-id", "cache-control"];

async function forward(req: NextRequest, path: string[], body: ArrayBuffer | undefined, token?: string) {
  const url = `${API_URL}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const headers: Record<string, string> = clientHeaders(req);
  const ct = req.headers.get("content-type");
  if (ct) headers["content-type"] = ct;
  if (token) headers["authorization"] = `Bearer ${token}`;
  return fetch(url, { method: req.method, headers, body, cache: "no-store", redirect: "manual" });
}

async function handle(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  if (path[0] !== "v1" || path.some((p) => p === ".." || p === "")) return problem(404, "not_found", "Not found", "");
  if (path[1] === "auth") return problem(404, "not_found", "Not found", "Use /api/auth for sign-in.");
  // returns fresh tokens: must go through /api/auth/password so they land in httpOnly cookies, not page JS
  if (path[1] === "me" && path[2] === "password") return problem(404, "not_found", "Not found", "Use /api/auth/password.");
  if (!csrfOk(req)) return problem(403, "csrf", "Blocked", "Request didn't come from this site.");
  let body: ArrayBuffer | undefined;
  if (!["GET", "HEAD"].includes(req.method)) {
    body = await req.arrayBuffer();
    if (body.byteLength > MAX_BODY) return problem(413, "payload_too_large", "Too large", "That upload is too big.");
  }
  let token = req.cookies.get(ACCESS)?.value;
  let fresh: Tokens | null = null;
  let r = await forward(req, path, body, token);
  const rt = req.cookies.get(REFRESH)?.value;
  if (r.status === 401 && rt) {
    fresh = await refresh(rt, req);
    if (fresh) {
      token = fresh.access_token;
      r = await forward(req, path, body, token);
    }
  }
  const headers = new Headers();
  for (const h of PASS_RESPONSE) {
    const v = r.headers.get(h);
    if (v) headers.set(h, v);
  }
  headers.set("x-content-type-options", "nosniff");
  const res = new NextResponse(r.body, { status: r.status, headers });
  if (fresh) setTokens(res, fresh);
  else if (r.status === 401 && rt) clearTokens(res);
  return res;
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
export const dynamic = "force-dynamic";
