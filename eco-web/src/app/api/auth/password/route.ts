// Change password while signed in. The API returns fresh tokens for this device; they go into httpOnly cookies and
// never reach page JavaScript.
import { NextRequest, NextResponse } from "next/server";
import { ACCESS, API_URL, csrfOk, problem, setTokens, clientHeaders } from "@/lib/server";

export async function POST(req: NextRequest) {
  if (!csrfOk(req)) return problem(403, "csrf", "Blocked", "Request didn't come from this site.");
  const token = req.cookies.get(ACCESS)?.value;
  if (!token) return problem(401, "unauthenticated", "Unauthenticated", "Sign in again.");
  const { current_password, new_password } = await req.json().catch(() => ({}));
  const r = await fetch(`${API_URL}/v1/me/password`, {
    method: "POST", cache: "no-store", headers: { "content-type": "application/json", ...clientHeaders(req), authorization: `Bearer ${token}` },
    body: JSON.stringify({ current_password, new_password }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return NextResponse.json(data, { status: r.status });
  const res = NextResponse.json({ message: data.message });
  setTokens(res, data.tokens);
  return res;
}
