"use client";
import Link from "next/link";
import { useState } from "react";
import { api, errorText } from "@/lib/api";
import { AuthFrame } from "@/components/AuthCard";
import { Button, Field, Input, Notice } from "@/components/ui";

export default function Forgot() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  return (
    <AuthFrame title="Reset your password" subtitle="We'll email you a link that works once, for 30 minutes.">
      <form className="flex flex-col gap-4" onSubmit={async (e) => {
        e.preventDefault(); setBusy(true); setMsg(null);
        try { const r = await api.auth<{ message: string }>("forgot", { email }); setMsg({ tone: "success", text: r.message }); }
        catch (x) { setMsg({ tone: "danger", text: errorText(x) }); }
        finally { setBusy(false); }
      }}>
        {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
        <Field label="Email" htmlFor="email"><Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Button type="submit" loading={busy}>Send reset link</Button>
        <p className="text-center text-[14px] text-muted"><Link href="/login" className="font-semibold text-orange-text underline">Back to sign in</Link></p>
      </form>
    </AuthFrame>
  );
}
