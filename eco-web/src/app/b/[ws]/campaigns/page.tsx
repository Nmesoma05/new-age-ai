"use client";
import { Megaphone, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { errorText, patch, post, useApi } from "@/lib/api";
import { CHANNELS, channelLabel, money, type ResultRow, type ResultsSummary } from "@/lib/biz";
import type { Campaign } from "@/lib/types";
import { useWs } from "@/components/Shell";
import { Badge, Button, Drawer, EmptyState, Field, Input, Markdown, Modal, Notice, PageHeader, Skeleton, Stat, StatusBadge, Textarea, Toggle, fmtDate, useToast } from "@/components/ui";

type Detail = { campaign: Campaign; results: ResultRow[]; summary: ResultsSummary };

function CampaignDrawer({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const { ws, base, canWrite } = useWs();
  const toast = useToast();
  const d = useApi<Detail>(`/v1/workspaces/${ws.id}/business/campaigns/${id}`);
  const c = d.data?.campaign, s = d.data?.summary;
  const plan = c?.plan as Record<string, any> | undefined;
  return (
    <Drawer open onClose={onClose} title={c?.name ?? "Campaign"}
      footer={c && canWrite && <div className="flex w-full flex-wrap gap-2">
        {(["draft", "active", "completed", "archived"] as const).filter((st) => st !== c.status).map((st) => (
          <Button key={st} variant="secondary" size="sm" onClick={async () => {
            try { await patch(`/v1/workspaces/${ws.id}/business/campaigns/${id}`, { status: st }); toast(`Marked ${st}`); d.reload(); onChanged(); } catch (e) { toast(errorText(e), "danger"); }
          }}>Mark {st}</Button>))}
        <span className="flex-1" /><Link className="inline-flex min-h-[36px] items-center text-[14px] font-semibold text-orange-text underline" href={`${base}/results?campaign=${id}`}>Record results</Link></div>}>
      {!c || !s ? <Skeleton className="h-64" /> : (
        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap items-center gap-2"><StatusBadge status={c.status} />
            <span className="text-[13px] text-muted">{c.start_date ? `${fmtDate(c.start_date)} – ${fmtDate(c.end_date!)}` : "No dates"} · {c.channels.map(channelLabel).join(", ")}</span></div>
          {c.status === "active" && <Notice>"Active" is your record that it's running. Nothing was launched from this app.</Notice>}
          {c.objective && <p>{c.objective}</p>}
          {c.budget_note && <p className="text-[14px] text-muted">Budget: {c.budget_note}</p>}
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Spend" value={money(s.totals.spend, s.currency)} /><Stat label="Leads" value={s.totals.leads ?? "–"} />
            <Stat label="Customers" value={s.totals.customers ?? "–"} /><Stat label="Cost per lead" value={money(s.totals.cost_per_lead, s.currency)} />
          </div>
          {d.data!.results.length === 0 && <p className="text-[14px] text-muted">No results recorded for this campaign yet.</p>}
          {plan?.creatives && <section><h3 className="mb-2 font-semibold">Ad copy from the plan</h3>
            <ul className="flex flex-col gap-2">{(plan.creatives as any[]).map((cr, i) => <li key={i} className="rounded-m bg-sunken p-3 text-[14px]">
              <Badge tone="d2">{channelLabel(cr.channel)}</Badge><div className="mt-1 font-semibold">{cr.headline}</div><p>{cr.primary_text}</p><p className="text-muted">CTA: {cr.call_to_action}</p></li>)}</ul></section>}
          {plan?.test_plan && <section><h3 className="mb-1 font-semibold">Test plan</h3><Markdown text={String(plan.test_plan)} /></section>}
          {s.caveats.length > 0 && <ul className="list-disc pl-5 text-[13px] text-muted">{s.caveats.map((x) => <li key={x}>{x}</li>)}</ul>}
        </div>)}
    </Drawer>
  );
}

export default function Campaigns() {
  const { ws, base, canWrite } = useWs();
  const toast = useToast();
  const router = useRouter();
  const open = useSearchParams().get("open");
  const list = useApi<Campaign[]>(`/v1/workspaces/${ws.id}/business/campaigns`);
  const [creating, setCreating] = useState(false);
  const [f, setF] = useState({ name: "", objective: "", start_date: "", end_date: "", channels: [] as string[], budget_note: "" });
  const setOpen = (id: string | null) => router.replace(id ? `${base}/campaigns?open=${id}` : `${base}/campaigns`);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Campaigns" description="Track campaigns you run yourself, from an AI ad plan or from scratch, and link results to them.">
        {canWrite && <Button icon={<Plus className="h-4 w-4" />} onClick={() => setCreating(true)}>New campaign</Button>}
      </PageHeader>
      {!list.data && <Skeleton className="h-40" />}
      {list.data?.length === 0 && <EmptyState tone="d2" icon={<Megaphone className="h-6 w-6" />} title="No campaigns yet"
        action={<Link className="font-semibold text-orange-text underline" href={`${base}/tools/ads`}>Plan one with AI</Link>}>Plan ads with the advertising tool, then turn the plan into a campaign.</EmptyState>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {list.data?.map((c) => (
          <button key={c.id} onClick={() => setOpen(c.id)} className="flex flex-col rounded-m border border-line bg-raised p-4 text-left transition hover:border-control hover:shadow-1">
            <div className="flex items-start justify-between gap-2"><span className="font-semibold">{c.name}</span><StatusBadge status={c.status} /></div>
            <span className="mt-1 text-[13px] text-muted">{c.start_date ? `${fmtDate(c.start_date)} – ${fmtDate(c.end_date!)}` : "No dates"}</span>
            <span className="mt-2 flex flex-wrap gap-1">{c.channels.map((ch) => <Badge key={ch}>{channelLabel(ch)}</Badge>)}</span>
          </button>))}
      </div>
      {open && <CampaignDrawer id={open} onClose={() => setOpen(null)} onChanged={list.reload} />}
      <Modal open={creating} onClose={() => setCreating(false)} title="New campaign" wide
        footer={<><Button variant="ghost" onClick={() => setCreating(false)}>Cancel</Button><Button disabled={!f.name.trim()} onClick={async () => {
          try {
            await post(`/v1/workspaces/${ws.id}/business/campaigns`, { ...f, start_date: f.start_date || null, end_date: f.end_date || null });
            toast("Campaign created"); setCreating(false); list.reload();
          } catch (e) { toast(errorText(e), "danger"); }
        }}>Create</Button></>}>
        <div className="flex flex-col gap-4">
          <Field label="Name" htmlFor="cpn"><Input id="cpn" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Objective" htmlFor="cpo"><Textarea id="cpo" rows={2} value={f.objective} onChange={(e) => setF({ ...f, objective: e.target.value })} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Starts" htmlFor="cps"><Input id="cps" type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></Field>
            <Field label="Ends" htmlFor="cpe"><Input id="cpe" type="date" value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} /></Field>
          </div>
          <Field label="Channels"><div className="flex flex-wrap gap-2">{CHANNELS.map((ch) => <Toggle key={ch.id} on={f.channels.includes(ch.id)}
            onChange={(on) => setF({ ...f, channels: on ? [...f.channels, ch.id] : f.channels.filter((x) => x !== ch.id) })}>{ch.label}</Toggle>)}</div></Field>
          <Field label="Budget note" htmlFor="cpb"><Input id="cpb" value={f.budget_note} onChange={(e) => setF({ ...f, budget_note: e.target.value })} /></Field>
        </div>
      </Modal>
    </div>
  );
}
