import { NextRequest, NextResponse } from "next/server";
import { API_URL, clearTokens, csrfOk, problem, clientHeaders } from "@/lib/server";

export async function POST(req: NextRequest) {
  if (!csrfOk(req)) return problem(403, "csrf", "Blocked", "Request didn't come from this site.");
  const { token, new_password } = await req.json().catch(() => ({}));
  const r = await fetch(`${API_URL}/v1/auth/password/reset`, {
    method: "POST", headers: { "content-type": "application/json", ...clientHeaders(req) }, cache: "no-store",
    body: JSON.stringify({ token, new_password }),
  });
  const res = NextResponse.json(await r.json().catch(() => ({})), { status: r.status });
  if (r.ok) clearTokens(res); // every session was revoked by the reset
  return res;
}
