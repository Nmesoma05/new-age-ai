import { NextRequest, NextResponse } from "next/server";
import { API_URL, csrfOk, problem, setTokens, clientHeaders } from "@/lib/server";

export async function POST(req: NextRequest) {
  if (!csrfOk(req)) return problem(403, "csrf", "Blocked", "Request didn't come from this site.");
  const input = await req.json().catch(() => ({}));
  const r = await fetch(`${API_URL}/v1/auth/signup`, {
    method: "POST", headers: { "content-type": "application/json", ...clientHeaders(req) }, cache: "no-store",
    body: JSON.stringify({ ...input, product: null }), // the Creator product is enabled during onboarding
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return NextResponse.json(data, { status: r.status });
  const res = NextResponse.json({ ok: true, user: data.user });
  setTokens(res, data.tokens);
  return res;
}
