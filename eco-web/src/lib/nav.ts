// Same-site redirect targets only (QA BUG-05). Browsers treat "/\host", "/\t/host" and similar as other sites, so a
// prefix check isn't enough: resolve against our own origin and require the origin to be unchanged.
export function safeNext(next: string | null | undefined, fallback = "/"): string {
  if (!next || typeof window === "undefined") return fallback;
  if (/[\\\u0000-\u001f\u007f]/.test(next) || !next.startsWith("/") || next.startsWith("//")) return fallback;
  try {
    const u = new URL(next, window.location.origin);
    return u.origin === window.location.origin ? u.pathname + u.search + u.hash : fallback;
  } catch {
    return fallback;
  }
}
