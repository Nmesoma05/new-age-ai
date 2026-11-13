"use client";
// The token arrives in the URL fragment (#token=...), which browsers never send to servers or in Referer headers.
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorText } from "@/lib/api";
import { AuthFrame } from "@/components/AuthCard";
import { Button, Field, Input, Notice } from "@/components/ui";

export default function Reset() {
  const [token, setToken] = useState<string | null>(null);
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => {
    const t = new URLSearchParams(location.hash.slice(1)).get("token");
    setToken(t ?? "");
    if (t) history.replaceState(null, "", "/reset-password"); // don't leave the token in history
  }, []);
  return (
    <AuthFrame title="Choose a new password" subtitle="This signs you out on every device.">
      {token === "" && <Notice tone="danger">This link is incomplete. <Link className="underline" href="/forgot-password">Ask for a new one</Link>.</Notice>}
      {done ? <div className="flex flex-col gap-4"><Notice tone="success">{done}</Notice><Link className="font-semibold text-orange-text underline" href="/login">Sign in</Link></div>
        : token && (
        <form className="flex flex-col gap-4" onSubmit={async (e) => {
          e.preventDefault(); setErr("");
          if (pw !== pw2) { setErr("The two passwords don't match."); return; }
          setBusy(true);
          try { const r = await api.auth<{ message: string }>("reset", { token, new_password: pw }); setDone(r.message); }
          catch (x) { setErr(errorText(x)); } finally { setBusy(false); }
        }}>
          {err && <Notice tone="danger">{err}</Notice>}
          <Field label="New password" htmlFor="pw" hint="At least 10 characters."><Input id="pw" type="password" autoComplete="new-password" minLength={10} maxLength={128} required value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
          <Field label="Repeat new password" htmlFor="pw2"><Input id="pw2" type="password" autoComplete="new-password" minLength={10} maxLength={128} required value={pw2} onChange={(e) => setPw2(e.target.value)} /></Field>
          <Button type="submit" loading={busy}>Change password</Button>
        </form>)}
    </AuthFrame>
  );
}
