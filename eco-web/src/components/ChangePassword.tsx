"use client";
import { useState } from "react";
import { api, errorText } from "@/lib/api";
import { Button, Card, Field, Input, SectionTitle, useToast } from "@/components/ui";

export default function ChangePassword() {
  const toast = useToast();
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Card className="flex flex-col gap-4">
      <SectionTitle>Your password</SectionTitle>
      <form className="flex flex-col gap-3" onSubmit={async (e) => {
        e.preventDefault(); setBusy(true);
        try { const r = await api.auth<{ message: string }>("password", { current_password: cur, new_password: pw }); toast(r.message); setCur(""); setPw(""); }
        catch (x) { toast(errorText(x), "danger"); } finally { setBusy(false); }
      }}>
        <Field label="Current password" htmlFor="cpw"><Input id="cpw" type="password" autoComplete="current-password" required value={cur} onChange={(e) => setCur(e.target.value)} /></Field>
        <Field label="New password" htmlFor="npw" hint="At least 10 characters. Other devices get signed out."><Input id="npw" type="password" autoComplete="new-password" minLength={10} maxLength={128} required value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
        <div><Button type="submit" loading={busy}>Change password</Button></div>
      </form>
    </Card>
  );
}
