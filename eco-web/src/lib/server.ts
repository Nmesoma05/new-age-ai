// Server-only helpers for the backend-for-frontend. Tokens live in httpOnly cookies, so page JavaScript can never
// read them; the browser only ever talks to this Next.js server, which talks to the API.
import "server-only";
import { NextRequest, NextResponse } from "next/server";

// A bare "host:port" (how Render hands over a private service's address) means plain http on the private network.
const rawApi = (process.env.API_URL || "http://localhost:8000").replace(/\/$/, "");
export const API_URL = /^https?:\/\//.test(rawApi) ? rawApi : `http://${rawApi}`;
export const ACCESS = "eco_at";
export const REFRESH = "eco_rt";
const secure = process.env.COOKIE_SECURE === "true";

export type Tokens = { access_token: string; refresh_token: string; expires_in: number };

export function setTokens(res: NextResponse, t: Tokens) {
  res.cookies.set(ACCESS, t.access_token, { httpOnly: true, secure, sameSite: "lax", path: "/", maxAge: t.expires_in });
  res.cookies.set(REFRESH, t.refresh_token, {
    httpOnly: true, secure, sameSite: "strict", path: "/api", maxAge: 60 * 60 * 24 * 30,
  });
  // Non-secret hint so middleware can redirect signed-out users without seeing a token.
  res.cookies.set("eco_session", "1", { httpOnly: true, secure, sameSite: "lax", path: "/", maxAge: 60 * 60 * 24 * 30 });
}

export function clearTokens(res: NextResponse) {
  for (const [name, path] of [[ACCESS, "/"], [REFRESH, "/api"], ["eco_session", "/"]] as const) {
    res.cookies.set(name, "", { httpOnly: true, secure, path, maxAge: 0 });
  }
}

/** Mutating requests must be same-origin and carry our custom header (a cross-site form can't add it). */
export function csrfOk(req: NextRequest): boolean {
  if (["GET", "HEAD", "OPTIONS"].includes(req.method)) return true;
  if (req.headers.get("x-eco-csrf") !== "1") return false;
  const origin = req.headers.get("origin");
  if (!origin) return true; // same-origin fetches from older browsers may omit it; the header check still holds
  try {
    return new URL(origin).host === req.headers.get("host");
  } catch {
    return false;
  }
}

export function problem(status: number, code: string, title: string, detail: string) {
  return NextResponse.json({ type: "about:blank", status, code, title, detail }, {
    status, headers: { "content-type": "application/problem+json" },
  });
}

// Who is really calling (QA BUG-10): the API would otherwise only ever see this server. The browser's user agent is
// always passed on. X-Forwarded-For is passed on only when this server sits behind a proxy that sets it
// (TRUST_FORWARDED_FOR=true, e.g. a load balancer or Vercel); otherwise a visitor could write their own.
const TRUST_XFF = process.env.TRUST_FORWARDED_FOR === "true";
export function clientHeaders(req: NextRequest): Record<string, string> {
  const h: Record<string, string> = {};
  const ua = req.headers.get("user-agent");
  if (ua) h["user-agent"] = ua.slice(0, 300);
  const xff = TRUST_XFF ? req.headers.get("x-forwarded-for") : null;
  if (xff) h["x-forwarded-for"] = xff.slice(0, 500);
  return h;
}

export async function refresh(rt: string, req?: NextRequest): Promise<Tokens | null> {
  const r = await fetch(`${API_URL}/v1/auth/refresh`, {
    method: "POST", headers: { "content-type": "application/json", ...(req ? clientHeaders(req) : {}) }, body: JSON.stringify({ refresh_token: rt }),
    cache: "no-store",
  });
  return r.ok ? ((await r.json()) as Tokens) : null;
}
