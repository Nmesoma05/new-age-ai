import { NextRequest, NextResponse } from "next/server";
import { API_URL, csrfOk, problem, setTokens, clientHeaders } from "@/lib/server";

export async function POST(req: NextRequest) {
  if (!csrfOk(req)) return problem(403, "csrf", "Blocked", "Request didn't come from this site.");
  const body = await req.text();
  const r = await fetch(`${API_URL}/v1/auth/login`, {
    method: "POST", headers: { "content-type": "application/json", ...clientHeaders(req) }, body, cache: "no-store",
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return NextResponse.json(data, { status: r.status });
  const res = NextResponse.json({ ok: true });
  setTokens(res, data);
  return res;
}
