"use client";
import { LogOut, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { ApiError, api, errorText, post, useApi } from "@/lib/api";
import type { OnboardingState, Platform } from "@/lib/types";
import { platformLabel } from "@/lib/types";
import { Logo } from "@/components/Logo";
import { PlatformPicker } from "@/components/PlatformPicker";
import { Badge, Button, EmptyState, Field, Input, Modal, Notice, PageHeader, Select, Skeleton } from "@/components/ui";

function Ring({ pct }: { pct: number }) {
  const r = 18, c = 2 * Math.PI * r;
  return (
    <svg width="48" height="48" viewBox="0 0 48 48" role="img" aria-label={`Profile ${pct}% complete`}>
      <circle cx="24" cy="24" r={r} fill="none" strokeWidth="5" className="stroke-sunken" />
      <circle cx="24" cy="24" r={r} fill="none" strokeWidth="5" strokeLinecap="round" className="stroke-orange"
        strokeDasharray={`${(pct / 100) * c} ${c}`} transform="rotate(-90 24 24)" />
      <text x="24" y="28" textAnchor="middle" className="fill-ink font-mono text-[11px] font-semibold">{pct}</text>
    </svg>
  );
}

export default function Clients() {
  const st = useApi<OnboardingState>("/v1/creator/onboarding");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ org_id: "", client_name: "", industry: "", platforms: ["instagram"] as Platform[] });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<{ text: string; limit?: boolean } | null>(null);
  const adminOrgs = st.data?.orgs.filter((o) => o.role === "owner" || o.role === "admin") ?? [];

  async function add() {
    setBusy(true); setErr(null);
    try {
      const res = await post<{ workspace_id: string }>("/v1/creator/clients", {
        org_id: f.org_id || adminOrgs[0]?.id,
        client: { client_name: f.client_name, industry: f.industry || null, platforms: f.platforms },
      });
      location.href = `/c/${res.workspace_id}/brand`;
    } catch (x) {
      setErr({ text: errorText(x), limit: x instanceof ApiError && x.code === "workspace_limit_reached" });
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen">
      <header className="flex items-center justify-between bg-sidebar px-4 py-3 sm:px-8">
        <Logo inverse division="creator" />
        <button onClick={async () => { await api.auth("logout").catch(() => 0); location.href = "/login"; }}
          className="inline-flex min-h-[40px] items-center gap-2 rounded-m px-3 text-[14px] font-semibold text-sidebar-ink hover:bg-sidebar-hover">
          <LogOut className="h-4 w-4" />Sign out</button>
      </header>
      <main className="mx-auto max-w-[1280px] px-4 py-8 sm:px-8">
        <PageHeader title="Your clients" description="Each client is a separate workspace with its own brand, content, calendar and reports.">
          <Button icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)} disabled={!adminOrgs.length}>Add client</Button>
        </PageHeader>
        {st.loading && !st.data && <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-36" />)}</div>}
        {st.error && <Notice tone="danger">{errorText(st.error)}</Notice>}
        {st.data && st.data.clients.length === 0 && (
          <EmptyState title="No clients yet" action={<Link className="font-semibold text-orange-text underline" href="/onboarding">Set up your first client</Link>}>
            Add a client to start drafting content and planning their calendar.</EmptyState>
        )}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {st.data?.clients.map((c) => (
            <Link key={c.workspace_id} href={`/c/${c.workspace_id}`}
              className="group rounded-m border border-line bg-raised p-5 transition hover:-translate-y-0.5 hover:border-control hover:shadow-1">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-[18px] font-semibold">{c.client_name || c.workspace_name}</div>
                  <div className="text-[13px] text-muted">{c.industry || "No industry set"} · {c.org_kind === "team" ? c.org_name : "Personal"}</div>
                </div>
                <Ring pct={c.profile_complete} />
              </div>
              <div className="mt-4 flex flex-wrap gap-1.5">
                {c.platforms.length ? c.platforms.map((p) => <Badge key={p}>{platformLabel(p)}</Badge>) : <span className="text-[13px] text-muted">No platforms yet</span>}
              </div>
              <div className="mt-4 text-[13px] font-semibold text-orange-text group-hover:underline">Open workspace →</div>
            </Link>
          ))}
        </div>
      </main>

      <Modal open={open} onClose={() => setOpen(false)} title="Add a client"
        footer={<><Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={add} loading={busy} disabled={!f.client_name.trim()}>Create workspace</Button></>}>
        <div className="flex flex-col gap-4">
          {err && <Notice tone={err.limit ? "warning" : "danger"} title={err.limit ? "Your plan's client limit is reached" : undefined}>
            {err.limit ? "Upgrade to add more clients. Online checkout isn't available in this version yet, so contact support to upgrade." : err.text}</Notice>}
          {adminOrgs.length > 1 && (
            <Field label="Add to" htmlFor="org"><Select id="org" value={f.org_id || adminOrgs[0].id} onChange={(e) => setF({ ...f, org_id: e.target.value })}>
              {adminOrgs.map((o) => <option key={o.id} value={o.id}>{o.kind === "personal" ? "Personal" : o.name} ({o.plan} plan)</option>)}</Select></Field>
          )}
          <Field label="Client or brand name" htmlFor="ncn"><Input id="ncn" value={f.client_name} onChange={(e) => setF({ ...f, client_name: e.target.value })} /></Field>
          <Field label="Industry" htmlFor="nin"><Input id="nin" value={f.industry} onChange={(e) => setF({ ...f, industry: e.target.value })} /></Field>
          <Field label="Platforms"><PlatformPicker value={f.platforms} onChange={(p) => setF({ ...f, platforms: p })} /></Field>
          <p className="text-[13px] text-muted">You'll add their brand voice, audience and goals on the next screen.</p>
        </div>
      </Modal>
    </div>
  );
}
