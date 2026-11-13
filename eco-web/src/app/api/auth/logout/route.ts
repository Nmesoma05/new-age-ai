import { NextRequest, NextResponse } from "next/server";
import { API_URL, REFRESH, clearTokens, csrfOk, problem, clientHeaders } from "@/lib/server";

export async function POST(req: NextRequest) {
  if (!csrfOk(req)) return problem(403, "csrf", "Blocked", "Request didn't come from this site.");
  const rt = req.cookies.get(REFRESH)?.value;
  if (rt) {
    await fetch(`${API_URL}/v1/auth/logout`, {
      method: "POST", headers: { "content-type": "application/json", ...clientHeaders(req) }, body: JSON.stringify({ refresh_token: rt }),
      cache: "no-store",
    }).catch(() => undefined);
  }
  const res = NextResponse.json({ ok: true });
  clearTokens(res);
  return res;
}
