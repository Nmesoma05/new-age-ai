import { NextRequest, NextResponse } from "next/server";

const PUBLIC = [/^\/manifest\.webmanifest$/, /^\/sw\.js$/, /^\/offline$/, /^\/icons\//, /^\/brand\//, /^\/privacy$/, /^\/terms$/, /^\/login/, /^\/signup/, /^\/forgot-password/, /^\/reset-password/, /^\/review\//, /^\/api\//, /^\/_next\//, /^\/favicon/];
const DEV = process.env.NODE_ENV !== "production";

// Content-Security-Policy with a fresh nonce per request (QA BUG-12): only scripts this server rendered can run,
// nothing can be framed or framing us, forms and fetches stay on this site, plugins are off.
function csp(nonce: string) {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${DEV ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob:",
    "worker-src 'self'",          // the offline-screen service worker (/sw.js)
    "manifest-src 'self'",
    `connect-src 'self'${DEV ? " ws:" : ""}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(DEV ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");
}

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const nonce = btoa(crypto.randomUUID());
  const policy = csp(nonce);
  let res: NextResponse;
  if (!PUBLIC.some((r) => r.test(pathname)) && !req.cookies.get("eco_session")) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname)}`;
    res = NextResponse.redirect(url);
  } else {
    const headers = new Headers(req.headers);
    headers.set("x-nonce", nonce);
    headers.set("content-security-policy", policy);  // Next reads this to put the nonce on its own scripts
    res = NextResponse.next({ request: { headers } });
  }
  if (!pathname.startsWith("/api/")) res.headers.set("content-security-policy", policy);
  return res;
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon).*)"] };
