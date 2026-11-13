"use client";
// Data-subject rights in the product (Nigeria Data Protection Act 2023, s.34): download everything, delete the account.
import { useState } from "react";
import { api, downloadUrl, errorText, post } from "@/lib/api";
import { Button, Card, Field, Input, LinkButton, Notice, SectionTitle } from "@/components/ui";

export default function YourData() {
  const [open, setOpen] = useState(false);
  const [pw, setPw] = useState("");
  const [word, setWord] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  return (
    <Card className="flex flex-col gap-4" id="your-data">
      <SectionTitle>Your data</SectionTitle>
      <p className="text-[14px] text-muted">Download a copy of everything we hold about you, or delete your account. See the <a className="underline" href="/privacy" target="_blank">Privacy Policy</a>.</p>
      <div className="flex flex-wrap gap-3">
        <LinkButton variant="secondary" href={downloadUrl("/v1/me/export")} download>Download my data</LinkButton>
        {!open && <Button variant="danger" onClick={() => setOpen(true)}>Delete my account</Button>}
      </div>
      {open && <form className="flex flex-col gap-3 rounded-m border border-danger/40 p-4" onSubmit={async (e) => {
        e.preventDefault(); setBusy(true); setErr("");
        try {
          await post("/v1/me/delete", { password: pw, confirm: word });
          await api.auth("logout").catch(() => undefined);
          location.href = "/login?deleted=1";
        } catch (x) { setErr(errorText(x)); setBusy(false); }
      }}>
        <Notice tone="danger" title="This can't be undone">You'll be signed out everywhere and your name and email are removed now. Workspaces you own close now and are erased, files included, within 30 days. Work you did in someone else's organisation stays with them, credited to "Deleted user".</Notice>
        {err && <Notice tone="danger">{err}</Notice>}
        <Field label="Your password" htmlFor="dpw"><Input id="dpw" type="password" autoComplete="current-password" required value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
        <Field label='Type DELETE to confirm' htmlFor="dword"><Input id="dword" required value={word} onChange={(e) => setWord(e.target.value)} autoComplete="off" /></Field>
        <div className="flex gap-3">
          <Button type="submit" variant="danger" loading={busy} disabled={word !== "DELETE" || !pw}>Delete my account</Button>
          <Button type="button" variant="ghost" onClick={() => { setOpen(false); setPw(""); setWord(""); setErr(""); }}>Cancel</Button>
        </div>
      </form>}
    </Card>
  );
}
