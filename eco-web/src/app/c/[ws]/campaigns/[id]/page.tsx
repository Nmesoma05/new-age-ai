"use client";
import { useParams, useRouter } from "next/navigation";
import { del, errorText, patch, useApi } from "@/lib/api";
import type { Campaign } from "@/lib/types";
import { platformLabel } from "@/lib/types";
import { useWs } from "@/components/Shell";
import { Badge, Card, ConfirmButton, LinkButton, Notice, PageHeader, SectionTitle, Select, Skeleton, StatusBadge, fmtDate, fmtTime, useToast } from "@/components/ui";

type Phase = { name: string; start_date: string; end_date: string; goal: string; activities: string[];
  deliverables: { platform: string; format: string; description: string }[] };

export default function CampaignDetail() {
  const { id } = useParams<{ id: string }>();
  const { ws, base, canWrite } = useWs();
  const router = useRouter();
  const toast = useToast();
  const c = useApi<Campaign>(`/v1/workspaces/${ws.id}/creator/campaigns/${id}`);
  if (c.error) return <Notice tone="danger">This campaign couldn't be found.</Notice>;
  if (!c.data) return <Skeleton className="h-64" />;
  const plan = c.data.plan as { phases?: Phase[]; kpis?: { metric: string; how_to_measure: string }[]; key_message?: string; audience?: string; risks?: string[] };
  const span = c.data.start_date && c.data.end_date ? [new Date(c.data.start_date).getTime(), new Date(c.data.end_date).getTime()] : null;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={c.data.name} eyebrow="Campaign" description={c.data.objective}>
        <label className="sr-only" htmlFor="cst">Status</label>
        <Select id="cst" className="w-auto" value={c.data.status} disabled={!canWrite} onChange={async (e) => {
          try { await patch(`/v1/workspaces/${ws.id}/creator/campaigns/${id}`, { status: e.target.value }); c.reload(); toast("Status updated"); }
          catch (x) { toast(errorText(x), "danger"); }
        }}>{["draft", "active", "completed", "archived"].map((s) => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}</Select>
        <LinkButton href={`${base}/calendar`}>Open calendar</LinkButton>
        {canWrite && <ConfirmButton label="Delete campaign? Calendar items stay." onConfirm={async () => { await del(`/v1/workspaces/${ws.id}/creator/campaigns/${id}`); router.push(`${base}/campaigns`); }}>Delete</ConfirmButton>}
      </PageHeader>
      <div className="flex flex-wrap gap-2"><StatusBadge status={c.data.status} />
        {c.data.start_date && <Badge>{fmtDate(c.data.start_date, { day: "numeric", month: "short", year: "numeric" })} – {c.data.end_date ? fmtDate(c.data.end_date, { day: "numeric", month: "short", year: "numeric" }) : "open"}</Badge>}
        {c.data.channels.map((ch) => <Badge key={ch} tone="d1">{platformLabel(ch)}</Badge>)}</div>
      {(plan.key_message || plan.audience) && <Card className="grid gap-4 sm:grid-cols-2">
        {plan.key_message && <div><div className="text-[12px] font-semibold uppercase tracking-[0.6px] text-muted">Key message</div><p className="mt-1 text-[17px]">{plan.key_message}</p></div>}
        {plan.audience && <div><div className="text-[12px] font-semibold uppercase tracking-[0.6px] text-muted">Audience</div><p className="mt-1">{plan.audience}</p></div>}
      </Card>}
      {plan.phases && plan.phases.length > 0 && (
        <section>
          <SectionTitle>Phases</SectionTitle>
          {span && <div className="relative mb-4 h-3 rounded-full bg-sunken" aria-hidden>
            {plan.phases.map((p, i) => {
              const a = (new Date(p.start_date).getTime() - span[0]) / Math.max(1, span[1] - span[0]);
              const b = (new Date(p.end_date).getTime() - span[0]) / Math.max(1, span[1] - span[0]);
              return <div key={i} className="absolute top-0 h-3 rounded-full border-2 border-cream" style={{ left: `${a * 100}%`, width: `${Math.max(2, (b - a) * 100)}%`, background: i % 2 ? "rgb(var(--orange))" : "rgb(var(--d1-creator))" }} />;
            })}</div>}
          <div className="grid gap-4 lg:grid-cols-2">
            {plan.phases.map((p, i) => (
              <Card key={i}>
                <div className="flex items-center justify-between gap-2"><h3 className="text-[16px] font-semibold">{p.name}</h3><span className="font-mono text-[12px] text-muted">{fmtDate(p.start_date)} – {fmtDate(p.end_date)}</span></div>
                <p className="mt-1 text-muted">{p.goal}</p>
                {p.activities.length > 0 && <ul className="mt-3 list-disc pl-5 text-[14px]">{p.activities.map((a, j) => <li key={j}>{a}</li>)}</ul>}
                {p.deliverables.length > 0 && <ul className="mt-3 flex flex-col gap-1.5 text-[14px]">{p.deliverables.map((d, j) => (
                  <li key={j} className="flex gap-2"><Badge tone="d1">{platformLabel(d.platform)}</Badge><span><span className="font-semibold">{d.format}:</span> {d.description}</span></li>))}</ul>}
              </Card>))}
          </div>
        </section>
      )}
      {plan.kpis && plan.kpis.length > 0 && <Card><SectionTitle>How to measure it</SectionTitle>
        <ul className="flex flex-col gap-2">{plan.kpis.map((k, i) => <li key={i}><span className="font-semibold">{k.metric}</span> <span className="text-muted">· {k.how_to_measure}</span></li>)}</ul>
        <p className="mt-3 text-[13px] text-muted">Record the results in Reports; nothing is measured automatically.</p></Card>}
      {c.data.budget_note && <Card><SectionTitle>Budget</SectionTitle><p>{c.data.budget_note}</p></Card>}
      <section>
        <SectionTitle right={<span className="font-mono text-[13px] text-muted">{Object.entries(c.data.counts ?? {}).filter(([, n]) => n).map(([k, n]) => `${n} ${k.replace("_manually", "")}`).join(" · ")}</span>}>Calendar</SectionTitle>
        {(c.data.calendar ?? []).length === 0 ? <p className="text-muted">No calendar items linked yet. When you plan the calendar with AI, choose this campaign to link the posts.</p> : (
          <ul className="divide-y divide-line rounded-m border border-line bg-raised">{c.data.calendar!.map((i) => (
            <li key={i.id} className="flex items-center gap-3 px-3 py-2.5"><span className="w-24 font-mono text-[12px] text-muted">{fmtDate(i.scheduled_for)} {fmtTime(i.scheduled_for)}</span>
              <span className="min-w-0 flex-1 truncate">{i.title}</span><span className="text-[13px] text-muted">{platformLabel(i.platform)}</span><StatusBadge status={i.status} /></li>))}</ul>
        )}
      </section>
    </div>
  );
}
