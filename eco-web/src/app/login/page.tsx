"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, errorText } from "@/lib/api";
import { safeNext } from "@/lib/nav";
import { AuthFrame } from "@/components/AuthCard";
import { Button, Field, Input, Notice } from "@/components/ui";

function LoginForm() {
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const target = () => safeNext(params.get("next"));
  return (
    <form className="flex flex-col gap-4" onSubmit={async (e) => {
      e.preventDefault(); setBusy(true); setErr("");
      try { await api.auth("login", { email, password }); location.href = target(); }
      catch (x) { setErr(errorText(x)); setBusy(false); }
    }}>
      {params.get("deleted") === "1" && !err && <Notice tone="success">Your account was deleted. Thanks for trying us.</Notice>}
      {err && <Notice tone="danger">{err}</Notice>}
      <Field label="Email" htmlFor="email"><Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
      <Field label="Password" htmlFor="password"><Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
      <Button type="submit" loading={busy}>Sign in</Button>
      <p className="text-center text-[14px]"><Link href="/forgot-password" className="font-semibold text-orange-text underline">Forgot your password?</Link></p>
      <p className="text-center text-[14px] text-muted">New here? <Link href="/signup" className="font-semibold text-orange-text underline">Create an account</Link></p>
    </form>
  );
}

export default function Login() {
  return <AuthFrame title="Welcome back" subtitle="Sign in to your workspaces."><Suspense><LoginForm /></Suspense></AuthFrame>;
}
