import { NextRequest, NextResponse } from "next/server";
import { API_URL, csrfOk, problem, clientHeaders } from "@/lib/server";

export async function POST(req: NextRequest) {
  if (!csrfOk(req)) return problem(403, "csrf", "Blocked", "Request didn't come from this site.");
  const { email } = await req.json().catch(() => ({ email: "" }));
  const r = await fetch(`${API_URL}/v1/auth/password/forgot`, {
    method: "POST", headers: { "content-type": "application/json", ...clientHeaders(req) }, cache: "no-store", body: JSON.stringify({ email }),
  });
  return NextResponse.json(await r.json().catch(() => ({})), { status: r.status });
}
