"use client";
import Link from "next/link";
import { useApi } from "@/lib/api";
import type { Asset, ClientProfile, Page } from "@/lib/types";
import { platformLabel } from "@/lib/types";
import { useWs } from "@/components/Shell";
import { Generating, ResearchForm, TextResult, useGenerate } from "@/components/studio";
import { Badge, Card, Notice, PageHeader, SectionTitle, fmtDate } from "@/components/ui";

export default function Research() {
  const { ws, base, canWrite } = useWs();
  const prof = useApi<ClientProfile>(`/v1/workspaces/${ws.id}/client-account`);
  const past = useApi<Page<Asset>>(`/v1/workspaces/${ws.id}/assets?limit=50`);
  const g = useGenerate();
  const reports = (past.data?.data ?? []).filter((a) => a.type === "research");
  return (
    <div>
      <PageHeader title="Audience & competitor research" description="Turn what you know about the audience and competitors into clear opportunities." />
      <div className="grid gap-6 xl:grid-cols-[minmax(320px,420px)_1fr]">
        <div className="flex flex-col gap-6">
          <Card>
            <SectionTitle right={<Link href={`${base}/brand`} className="text-[14px] font-semibold text-orange-text">Edit</Link>}>What the analysis will use</SectionTitle>
            <div className="text-[14px]"><span className="font-semibold">Audience:</span> {prof.data?.audience.summary || <span className="text-muted">Not described yet</span>}</div>
            <div className="mt-3 text-[14px] font-semibold">Competitors</div>
            {(prof.data?.competitors ?? []).length === 0 ? <p className="text-[14px] text-muted">None added. <Link className="underline" href={`${base}/brand`}>Add competitor notes</Link> for a comparison.</p> : (
              <ul className="mt-1 flex flex-col gap-2">{prof.data!.competitors.map((c, i) => (
                <li key={i} className="rounded-s bg-sunken p-2 text-[14px]"><div className="flex items-center gap-2 font-semibold">{c.name}{c.platform && <Badge tone="d1">{platformLabel(c.platform)}</Badge>}</div>
                  {c.notes && <div className="text-muted">{c.notes}</div>}</li>))}</ul>
            )}
          </Card>
          <Card><ResearchForm onRun={g.run} busy={g.busy} disabled={!canWrite} /></Card>
        </div>
        <section className="min-w-0" aria-live="polite">
          {g.error && <Notice tone="danger">{g.error}</Notice>}
          {g.busy && <Generating label="Analysing…" />}
          {g.result && <TextResult ex={g.result} />}
          {!g.result && !g.busy && (
            <Card><SectionTitle>Past research</SectionTitle>
              {reports.length === 0 ? <p className="text-muted">Saved analyses appear here.</p> : (
                <ul className="divide-y divide-line">{reports.map((r) => <li key={r.id}><Link href={`${base}/library?open=${r.id}`} className="flex justify-between gap-2 py-2 hover:underline">
                  <span className="truncate">{r.title}</span><span className="text-[13px] text-muted">{fmtDate(r.created_at)}</span></Link></li>)}</ul>
              )}</Card>
          )}
        </section>
      </div>
    </div>
  );
}
