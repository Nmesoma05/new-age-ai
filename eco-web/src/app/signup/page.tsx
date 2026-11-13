"use client";
import Link from "next/link";
import { useState } from "react";
import { api, errorText } from "@/lib/api";
import { AuthFrame } from "@/components/AuthCard";
import { Button, Field, Input, Notice } from "@/components/ui";

export default function Signup() {
  const [f, setF] = useState({ display_name: "", email: "", password: "" });
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <AuthFrame title="Create your account" subtitle="Free plan: 1 workspace and 30 AI generations a month.">
      <form className="flex flex-col gap-4" onSubmit={async (e) => {
        e.preventDefault(); setBusy(true); setErr("");
        try {
          const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
          await api.auth("signup", { ...f, accept_terms: agree });
          await api.send("PATCH", "/v1/me", { timezone: tz }).catch(() => undefined); // calendar times in your zone
          location.href = "/start";
        } catch (x) { setErr(errorText(x)); setBusy(false); }
      }}>
        {err && <Notice tone="danger">{err}</Notice>}
        <Field label="Your name" htmlFor="name"><Input id="name" required autoComplete="name" value={f.display_name} onChange={set("display_name")} /></Field>
        <Field label="Email" htmlFor="email"><Input id="email" type="email" required autoComplete="email" value={f.email} onChange={set("email")} /></Field>
        <Field label="Password" htmlFor="password" hint="At least 10 characters.">
          <Input id="password" type="password" required minLength={10} autoComplete="new-password" value={f.password} onChange={set("password")} /></Field>
        <label className="flex items-start gap-3 text-[14px] leading-[20px]">
          <input type="checkbox" required checked={agree} onChange={(e) => setAgree(e.target.checked)} className="h-6 w-6 shrink-0 accent-orange" />
          <span>I agree to the <Link href="/terms" target="_blank" className="font-semibold underline">Terms of Service</Link> and the <Link href="/privacy" target="_blank" className="font-semibold underline">Privacy Policy</Link>.</span>
        </label>
        <Button type="submit" loading={busy} disabled={!agree}>Create account</Button>
        <p className="text-center text-[14px] text-muted">Already have one? <Link href="/login" className="font-semibold text-orange-text underline">Sign in</Link></p>
      </form>
    </AuthFrame>
  );
}
