"use client";
import { Download, Plus, Trash2, Upload } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { api, del, downloadUrl, errorText, post, useApi } from "@/lib/api";
import { CHANNELS, channelLabel, money, type ResultRow, type ResultsSummary } from "@/lib/biz";
import type { Campaign } from "@/lib/types";
import { useWs } from "@/components/Shell";
import { Button, Card, EmptyState, Field, Input, LinkButton, Modal, Notice, PageHeader, SectionTitle, Select, Skeleton, Stat, Tabs, Textarea, fmtDate, num, useToast } from "@/components/ui";

const iso = (d: Date) => d.toISOString().slice(0, 10);
const PRESETS = { "30": 29, "90": 89, "365": 364 } as const;
const METRICS = ["spend", "impressions", "clicks", "leads", "customers", "revenue"] as const;

export default function Results() {
  const { ws, base, canWrite } = useWs();
  const toast = useToast();
  const campaign = useSearchParams().get("campaign");
  const [range, setRange] = useState<keyof typeof PRESETS>("30");
  const end = iso(new Date());
  const start = iso(new Date(Date.now() - PRESETS[range] * 86400000));
  const q = `start=${start}&end=${end}`;
  const report = useApi<ResultsSummary>(`/v1/workspaces/${ws.id}/business/report?${q}`);
  const rows = useApi<ResultRow[]>(`/v1/workspaces/${ws.id}/business/results?${q}`);
  const camps = useApi<Campaign[]>(`/v1/workspaces/${ws.id}/business/campaigns`);
  const [adding, setAdding] = useState(!!campaign);
  const blank = { channel: "whatsapp", campaign_id: campaign ?? "", period_start: start, period_end: end, currency: "",
    spend: "", impressions: "", clicks: "", leads: "", customers: "", revenue: "", notes: "" };
  const [f, setF] = useState(blank);
  const [csvErr, setCsvErr] = useState("");
  const file = useRef<HTMLInputElement>(null);
  const reload = () => { report.reload(); rows.reload(); };
  const s = report.data, cur = s?.currency;
  const hasFigure = METRICS.some((m) => f[m] !== "");

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Results & reports" description="Record what your marketing produced, by channel. The maths is done by the app; AI analysis only uses these figures.">
        {canWrite && <>
          <input ref={file} type="file" accept=".csv,text/csv" className="hidden" onChange={async (e) => {
            const fl = e.target.files?.[0]; if (!fl) return;
            const fd = new FormData(); fd.append("file", fl);
            if (campaign) fd.append("campaign_id", campaign);
            setCsvErr("");
            try { const r = await api.upload<{ imported: number }>(`/v1/workspaces/${ws.id}/business/results/import`, fd); toast(`Imported ${r.imported} row(s)`); reload(); }
            catch (x) { setCsvErr(errorText(x)); }
            e.target.value = "";
          }} />
          <Button variant="secondary" icon={<Upload className="h-4 w-4" />} onClick={() => file.current?.click()}>Import CSV</Button>
          <Button icon={<Plus className="h-4 w-4" />} onClick={() => { setF(blank); setAdding(true); }}>Add results</Button></>}
      </PageHeader>
      {csvErr && <Notice tone="danger" title="Nothing was imported">{csvErr}</Notice>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs value={range} onChange={setRange} items={[{ id: "30", label: "30 days" }, { id: "90", label: "90 days" }, { id: "365", label: "12 months" }]} />
        <div className="flex flex-wrap gap-2">
          <LinkButton href={downloadUrl(`/v1/workspaces/${ws.id}/business/report/export?format=html&${q}`)} download><Download className="h-4 w-4" />Report</LinkButton>
          <LinkButton href={downloadUrl(`/v1/workspaces/${ws.id}/business/report/export?format=csv&${q}`)} download>CSV</LinkButton>
          <LinkButton href={`${base}/tools/report`}>AI analysis</LinkButton>
        </div>
      </div>
      {!s ? <Skeleton className="h-28" /> : <>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Spend" value={money(s.totals.spend, cur)} /><Stat label="Leads" value={num(s.totals.leads)} hint={s.totals.cost_per_lead !== null ? `${money(s.totals.cost_per_lead, cur)} each` : undefined} />
          <Stat label="Customers" value={num(s.totals.customers)} hint={s.totals.lead_to_customer_pct !== null ? `${s.totals.lead_to_customer_pct}% of leads` : undefined} />
          <Stat label="Revenue" value={money(s.totals.revenue, cur)} hint={s.totals.return_on_spend !== null ? `${s.totals.return_on_spend}× spend` : undefined} />
        </div>
        <Card>
          <SectionTitle>By channel</SectionTitle>
          {s.by_channel.length === 0 ? <EmptyState tone="d2" title="No results in this period">Add figures by hand or import a CSV with columns: channel, period_start, period_end, spend, leads, customers, revenue.</EmptyState> : (
            <div className="overflow-x-auto"><table className="w-full min-w-[640px] text-[14px]">
              <thead className="bg-sunken text-left text-[13px]"><tr>{["Channel", "Spend", "Leads", "Customers", "Revenue", "Cost per lead", "Return on spend"].map((h) => <th key={h} className="p-2">{h}</th>)}</tr></thead>
              <tbody>{s.by_channel.map((c) => <tr key={c.channel} className="border-t border-line font-mono">
                <td className="p-2 font-sans font-semibold">{channelLabel(c.channel)}</td><td className="p-2">{money(c.spend, cur)}</td><td className="p-2">{num(c.leads)}</td>
                <td className="p-2">{num(c.customers)}</td><td className="p-2">{money(c.revenue, cur)}</td><td className="p-2">{money(c.cost_per_lead, cur)}</td>
                <td className="p-2">{c.return_on_spend === null ? "–" : `${c.return_on_spend}×`}</td></tr>)}</tbody>
            </table></div>)}
          <ul className="mt-3 list-disc pl-5 text-[13px] text-muted">{s.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
        </Card></>}
      <Card>
        <SectionTitle>Recorded rows</SectionTitle>
        {rows.data?.length === 0 && <p className="text-[14px] text-muted">None in this period.</p>}
        <ul className="divide-y divide-line">{rows.data?.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-3 py-2 text-[14px]">
            <span className="w-40 font-semibold">{channelLabel(r.channel)}</span>
            <span className="text-muted">{fmtDate(r.period_start)} – {fmtDate(r.period_end)}</span>
            <span className="flex-1 font-mono text-[13px]">{METRICS.filter((m) => r[m] !== null).map((m) => `${m} ${m === "spend" || m === "revenue" ? money(r[m], r.currency) : num(r[m])}`).join(" · ")}</span>
            <span className="text-[12px] text-muted">{r.source === "csv_import" ? "CSV" : "Manual"}</span>
            {canWrite && <button aria-label="Delete row" className="grid h-9 w-9 place-items-center rounded-m text-muted hover:bg-sunken hover:text-danger"
              onClick={async () => { try { await del(`/v1/workspaces/${ws.id}/business/results/${r.id}`); toast("Deleted"); reload(); } catch (e) { toast(errorText(e), "danger"); } }}><Trash2 className="h-4 w-4" /></button>}
          </li>))}</ul>
      </Card>
      <Modal open={adding} onClose={() => setAdding(false)} title="Add results" wide
        footer={<><Button variant="ghost" onClick={() => setAdding(false)}>Cancel</Button><Button disabled={!hasFigure || f.period_end < f.period_start} onClick={async () => {
          const body: Record<string, unknown> = { channel: f.channel, period_start: f.period_start, period_end: f.period_end, notes: f.notes,
            campaign_id: f.campaign_id || null, currency: f.currency || null };
          for (const m of METRICS) if (f[m] !== "") body[m] = m === "spend" || m === "revenue" ? f[m] : Number(f[m]);
          try { await post(`/v1/workspaces/${ws.id}/business/results`, body); toast("Results saved"); setAdding(false); reload(); } catch (e) { toast(errorText(e), "danger"); }
        }}>Save</Button></>}>
        <div className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Channel" htmlFor="rc"><Select id="rc" value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })}>{CHANNELS.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</Select></Field>
            <Field label="Campaign (optional)" htmlFor="rcp"><Select id="rcp" value={f.campaign_id} onChange={(e) => setF({ ...f, campaign_id: e.target.value })}>
              <option value="">None</option>{camps.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
            <Field label="From" htmlFor="rfs"><Input id="rfs" type="date" value={f.period_start} onChange={(e) => setF({ ...f, period_start: e.target.value })} /></Field>
            <Field label="To" htmlFor="rfe"><Input id="rfe" type="date" value={f.period_end} onChange={(e) => setF({ ...f, period_end: e.target.value })} /></Field>
          </div>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            {METRICS.map((m) => <Field key={m} label={m[0].toUpperCase() + m.slice(1)} htmlFor={`rm-${m}`}><Input id={`rm-${m}`} type="number" min={0} step={m === "spend" || m === "revenue" ? "0.01" : "1"} value={f[m]} onChange={(e) => setF({ ...f, [m]: e.target.value })} /></Field>)}
          </div>
          <div className="grid gap-4 sm:grid-cols-[120px_1fr]">
            <Field label="Currency" htmlFor="rcur" hint="Blank = your budget currency"><Input id="rcur" maxLength={3} value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value.toUpperCase() })} /></Field>
            <Field label="Notes" htmlFor="rn"><Textarea id="rn" rows={1} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
          </div>
          <p className="text-[13px] text-muted">Leave a figure empty if you don't know it. Empty is shown as “–”, never as 0.</p>
        </div>
      </Modal>
    </div>
  );
}
