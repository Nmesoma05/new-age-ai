"use client";
import { MapPin, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { ApiError, errorText, post, useApi } from "@/lib/api";
import type { BusinessSummary } from "@/lib/biz";
import { TopBar } from "@/components/TopBar";
import { Badge, Button, EmptyState, Field, Input, Modal, Notice, PageHeader, Select, Skeleton } from "@/components/ui";

type State = { orgs: { id: string; name: string; kind: string; role: string; plan: string }[]; businesses: BusinessSummary[] };
type Cats = { categories: { key: string; label: string }[]; stages: { key: string; label: string }[] };

export default function Businesses() {
  const st = useApi<State>("/v1/business/onboarding");
  const cats = useApi<Cats>("/v1/business/categories");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ org_id: "", business_name: "", industry: "", category: "other" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<{ text: string; limit?: boolean } | null>(null);
  const adminOrgs = st.data?.orgs.filter((o) => o.role === "owner" || o.role === "admin") ?? [];
  const label = (k: string | null, list?: { key: string; label: string }[]) => list?.find((x) => x.key === k)?.label ?? k ?? "";

  async function add() {
    setBusy(true); setErr(null);
    try {
      const res = await post<{ workspace_id: string }>("/v1/business/businesses", {
        org_id: f.org_id || adminOrgs[0]?.id,
        profile: { business_name: f.business_name, industry: f.industry, category: f.category } });
      location.href = `/b/${res.workspace_id}/profile`;
    } catch (x) {
      setErr({ text: errorText(x), limit: x instanceof ApiError && x.code === "workspace_limit_reached" });
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen">
      <TopBar />
      <main className="mx-auto max-w-[1280px] px-4 py-8 sm:px-8">
        <PageHeader title="Your businesses" description="Each business has its own profile, strategy, saved work and results. Nothing is shared between them.">
          <Button icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)} disabled={!adminOrgs.length}>Add business</Button>
        </PageHeader>
        {st.loading && !st.data && <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-36" />)}</div>}
        {st.error && <Notice tone="danger">{errorText(st.error)}</Notice>}
        {st.data && st.data.businesses.length === 0 && (
          <EmptyState tone="d2" title="No businesses yet" action={<Link className="font-semibold text-orange-text underline" href="/business/onboarding">Set up your business</Link>}>
            Tell us about your business and get a marketing profile built around it.</EmptyState>)}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {st.data?.businesses.map((b) => (
            <Link key={b.workspace_id} href={`/b/${b.workspace_id}`}
              className="group flex flex-col rounded-m border border-line bg-raised p-5 transition hover:-translate-y-0.5 hover:border-control hover:shadow-1">
              <div className="truncate text-[18px] font-semibold">{b.business_name || b.workspace_name}</div>
              <div className="mt-1 flex items-center gap-1 text-[13px] text-muted"><MapPin className="h-3.5 w-3.5" />{b.location || "No location yet"}</div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                <Badge tone="d2">{label(b.category, cats.data?.categories)}</Badge><Badge>{label(b.stage, cats.data?.stages)}</Badge>
                {b.has_intelligence ? <Badge>Profile built</Badge> : <Badge tone="orange">Profile not built</Badge>}
              </div>
              <div className="mt-4 flex items-center gap-2"><div className="h-1.5 flex-1 overflow-hidden rounded-full bg-sunken">
                <div className="h-full bg-d2" style={{ width: `${b.profile_complete}%` }} /></div>
                <span className="font-mono text-[12px] text-muted">{b.profile_complete}%</span></div>
              <div className="mt-4 text-[13px] font-semibold text-orange-text group-hover:underline">Open →</div>
            </Link>))}
        </div>
      </main>
      <Modal open={open} onClose={() => setOpen(false)} title="Add a business"
        footer={<><Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={add} loading={busy} disabled={!f.business_name.trim() || !f.industry.trim()}>Create workspace</Button></>}>
        <div className="flex flex-col gap-4">
          {err && <Notice tone={err.limit ? "warning" : "danger"} title={err.limit ? "Your plan's workspace limit is reached" : undefined}>
            {err.limit ? "Upgrade to add more businesses. Online checkout isn't available in this version yet, so contact support to upgrade." : err.text}</Notice>}
          {adminOrgs.length > 1 && (
            <Field label="Add to" htmlFor="org"><Select id="org" value={f.org_id || adminOrgs[0].id} onChange={(e) => setF({ ...f, org_id: e.target.value })}>
              {adminOrgs.map((o) => <option key={o.id} value={o.id}>{o.kind === "personal" ? "Personal" : o.name} ({o.plan} plan)</option>)}</Select></Field>)}
          <Field label="Business name" htmlFor="nbn"><Input id="nbn" value={f.business_name} onChange={(e) => setF({ ...f, business_name: e.target.value })} /></Field>
          <Field label="Industry" htmlFor="nbi"><Input id="nbi" value={f.industry} onChange={(e) => setF({ ...f, industry: e.target.value })} /></Field>
          <Field label="Category" htmlFor="nbc"><Select id="nbc" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
            {cats.data?.categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</Select></Field>
          <p className="text-[13px] text-muted">You'll fill in the rest of the profile on the next screen.</p>
        </div>
      </Modal>
    </div>
  );
}
