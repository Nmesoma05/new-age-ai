"use client";
// Browser-side API access. Everything goes through the same-origin proxy; no token or key is ever in this bundle.
import { useCallback, useEffect, useRef, useState } from "react";

export class ApiError extends Error {
  constructor(public status: number, public code: string, public title: string, public detail: string,
              public extra: Record<string, unknown> = {}) {
    super(detail || title);
  }
}

const CSRF = { "x-eco-csrf": "1" };

// `signIn`: a 401 from a sign-in/recovery call means "wrong details", not "session expired" (QA BUG-08).
async function parse<T>(r: Response, signIn = false): Promise<T> {
  if (r.status === 204) return undefined as T;
  const ct = r.headers.get("content-type") || "";
  const body = ct.includes("json") ? await r.json().catch(() => ({})) : await r.text();
  if (!r.ok) {
    const b = (typeof body === "object" ? body : {}) as Record<string, unknown>;
    if (r.status === 401 && !signIn && typeof window !== "undefined" && !location.pathname.startsWith("/review")) {
      location.href = `/login?next=${encodeURIComponent(location.pathname)}`;
    }
    const detail = (b.detail as string) || (Array.isArray(b.errors) ? "Please check the highlighted fields." : "");
    throw new ApiError(r.status, (b.code as string) || "error", (b.title as string) || "Something went wrong", detail, b);
  }
  return body as T;
}

export const api = {
  get: <T,>(path: string) => fetch(`/api/proxy${path}`, { cache: "no-store" }).then((r) => parse<T>(r)),
  send: <T,>(method: "POST" | "PUT" | "PATCH" | "DELETE", path: string, body?: unknown) =>
    fetch(`/api/proxy${path}`, {
      method, headers: { ...CSRF, ...(body !== undefined ? { "content-type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }).then((r) => parse<T>(r)),
  upload: <T,>(path: string, form: FormData) =>
    fetch(`/api/proxy${path}`, { method: "POST", headers: CSRF, body: form }).then((r) => parse<T>(r)),
  auth: <T,>(path: "login" | "signup" | "logout" | "forgot" | "reset" | "password", body?: unknown) =>
    fetch(`/api/auth/${path}`, {
      method: "POST", headers: { ...CSRF, "content-type": "application/json" }, body: JSON.stringify(body ?? {}),
    }).then((r) => parse<T>(r, true)),
};

export const post = <T,>(p: string, b?: unknown) => api.send<T>("POST", p, b ?? {});
export const put = <T,>(p: string, b: unknown) => api.send<T>("PUT", p, b);
export const patch = <T,>(p: string, b: unknown) => api.send<T>("PATCH", p, b);
export const del = (p: string) => api.send<void>("DELETE", p);
export const downloadUrl = (p: string) => `/api/proxy${p}`;

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const rows = e.extra?.rows as { row: number; message: string }[] | undefined;
    if (rows?.length) return `${e.title}. ${e.detail} ` + rows.map((r) => `Row ${r.row}: ${r.message}`).join(" ");
    const errs = e.extra?.errors as { loc: (string | number)[]; msg: string }[] | undefined;
    if (errs?.length) return errs.map((x) => `${x.loc.filter((l) => l !== "body").join(".")}: ${x.msg}`).join("; ");
    return e.detail ? `${e.title}. ${e.detail}` : e.title;
  }
  return "Couldn't reach the server. Check your connection and try again.";
}

/** Load a resource; `reload()` refetches. Keeps the last good data while reloading. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | undefined>();
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [loading, setLoading] = useState(!!path);
  const seq = useRef(0);
  const load = useCallback(async () => {
    if (!path) return;
    const n = ++seq.current;
    setLoading(true);
    try {
      const d = await api.get<T>(path);
      if (n === seq.current) {
        setData(d);
        setError(null);
      }
    } catch (e) {
      if (n === seq.current) setError(e as Error);
    } finally {
      if (n === seq.current) setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    load();
  }, [load]);
  return { data, error, loading, reload: load, setData };
}
