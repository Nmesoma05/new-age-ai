"use client";
import { ArrowRight, BarChart3, Bot, CheckCircle2, ShieldCheck, Sparkles, Target } from "lucide-react";
import Link from "next/link";
import { useApi } from "@/lib/api";
import { channelLabel, money, tool, type ResultsSummary } from "@/lib/biz";
import type { Asset, Campaign } from "@/lib/types";
import { useWs } from "@/components/Shell";
import { Card, EmptyState, Notice, SectionTitle, Skeleton, Stat, StatusBadge, fmtDate } from "@/components/ui";

type Overview = {
  business: null | { name: string; category_label: string; stage_label: string; location: string | null; currency: string | null;
    profile_complete: number; has_intelligence: boolean; summary: string | null; priorities: string[] };
  next_steps: { tool: string; title: string; why: string }[]; saved: Record<string, number>; recent: Asset[];
  projects: { id: string; name: string }[]; campaigns: Campaign[]; pending_approvals: number; results_30d: ResultsSummary;
  plan: { name: string; ai_unlimited: boolean; free_remaining: number | null; free_limit: number | null };
};
const STEP_HREF: Record<string, string> = { profile: "/profile", results: "/results" };

export default function BizDashboard() {
  const { ws, base } = useWs();
  const { data, error } = useApi<Overview>(`/v1/workspaces/${ws.id}/business/overview`);
  if (error) return <Notice tone="danger">Couldn't load the dashboard. Refresh to try again.</Notice>;
  if (!data) return <div className="flex flex-col gap-4"><Skeleton className="h-40" /><div className="grid gap-4 sm:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}</div></div>;
  const b = data.business, r = data.results_30d, cur = r.currency;
  const savedTotal = Object.values(data.saved).reduce((a, n) => a + n, 0);
  return (
    <div className="flex flex-col gap-8">
      <section className="relative overflow-hidden rounded-l bg-d2 p-6 text-on-division sm:p-8">
        <div className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-orange/30 blur-3xl" aria-hidden />
        <div className="relative">
          <div className="text-[12px] font-semibold uppercase tracking-[0.6px]">{b ? `${b.category_label} · ${b.stage_label}` : "Business"}</div>
          <h1 className="mt-1 font-display text-[32px] font-bold leading-[38px] tracking-[-0.5px] sm:text-[40px] sm:leading-[44px]">{b?.name ?? ws.name}</h1>
          <p className="mt-2 max-w-[65ch] opacity-90">{b?.summary || (b?.location ? b.location : "Add your business profile to get started")}</p>
          <div className="mt-5 flex flex-wrap gap-2">
            <Link href={`${base}/tools`} className="inline-flex min-h-[40px] items-center gap-2 rounded-m bg-orange px-4 text-[14px] font-semibold text-on-orange transition hover:brightness-95">
              <Sparkles className="h-4 w-4" />Strategy tools</Link>
            <Link href={`${base}/strategist`} className="inline-flex min-h-[40px] items-center gap-2 rounded-m border border-cream/60 bg-black/20 px-4 text-[14px] font-semibold hover:bg-black/30"><Bot className="h-4 w-4" />Ask the strategist</Link>
            <Link href={`${base}/results`} className="inline-flex min-h-[40px] items-center gap-2 rounded-m border border-cream/60 bg-black/20 px-4 text-[14px] font-semibold hover:bg-black/30"><BarChart3 className="h-4 w-4" />Record results</Link>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Profile" value={`${b?.profile_complete ?? 0}%`} hint={b?.has_intelligence ? "Intelligence profile built" : "Intelligence profile not built"} />
        <Stat label="Saved work" value={savedTotal} hint={`${data.projects.length} active project(s)`} />
        <Stat label="Leads, 30 days" value={r.totals.leads ?? "–"} hint={r.rows ? `${r.rows} result row(s) recorded` : "Nothing recorded yet"} />
        <Stat label="Spend, 30 days" value={money(r.totals.spend, cur)} hint={r.totals.cost_per_lead !== null ? `${money(r.totals.cost_per_lead, cur)} per lead` : undefined} />
      </div>
      {data.pending_approvals > 0 && <Notice tone="warning" title={`${data.pending_approvals} request(s) awaiting approval`}>
        <Link className="underline" href={`${base}/approvals`}>Review them</Link>. Nothing is launched, paid or sent from this app.</Notice>}

      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <Card>
          <SectionTitle>Recommended next</SectionTitle>
          <p className="-mt-2 mb-3 text-[14px] text-muted">Picked for your stage and type of business.</p>
          <ol className="flex flex-col gap-2">
            {data.next_steps.map((s, i) => {
              const href = base + (STEP_HREF[s.tool] ?? `/tools/${s.tool}`);
              return (
                <li key={s.tool + i}><Link href={href} className="group flex items-start gap-3 rounded-m border border-line p-3 transition hover:border-control hover:bg-sunken/50">
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-d2-soft font-mono text-[13px] font-semibold text-d2">{i + 1}</span>
                  <span className="min-w-0 flex-1"><span className="block font-semibold">{s.title}</span><span className="block text-[14px] text-muted">{s.why}</span></span>
                  <ArrowRight className="mt-1 h-4 w-4 text-muted group-hover:text-ink" /></Link></li>);
            })}
            {data.next_steps.length === 0 && <li className="flex items-center gap-2 text-[14px]"><CheckCircle2 className="h-4 w-4 text-success" />You're set up. Keep recording results.</li>}
          </ol>
        </Card>
        <Card>
          <SectionTitle right={<Link href={`${base}/profile`} className="text-[14px] font-semibold text-orange-text">Profile <ArrowRight className="inline h-4 w-4" /></Link>}>Your priorities</SectionTitle>
          {b?.priorities?.length ? <ul className="flex flex-col gap-2">{b.priorities.map((p, i) => <li key={i} className="flex gap-2 text-[15px]"><Target className="mt-0.5 h-4 w-4 shrink-0 text-d2" />{p}</li>)}</ul>
            : <EmptyState tone="d2" title="No priorities yet" action={<Link className="font-semibold text-orange-text underline" href={`${base}/tools/intelligence`}>Build your profile</Link>}>Your Intelligence Profile sets them.</EmptyState>}
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <SectionTitle right={<Link href={`${base}/work`} className="text-[14px] font-semibold text-orange-text">All work <ArrowRight className="inline h-4 w-4" /></Link>}>Recent work</SectionTitle>
          {data.recent.length === 0 ? <EmptyState tone="d2" title="Nothing saved yet">Run a strategy tool and save the result.</EmptyState> : (
            <ul className="divide-y divide-line">{data.recent.map((a) => (
              <li key={a.id}><Link href={`${base}/work?open=${a.id}`} className="flex items-center gap-3 py-2.5 hover:underline">
                <span className="min-w-0 flex-1 truncate font-semibold">{a.title}</span>
                <span className="text-[13px] text-muted">{tool(a.tags[0])?.title ?? a.type} · {fmtDate(a.updated_at)}</span></Link></li>))}</ul>)}
        </Card>
        <Card>
          <SectionTitle right={<Link href={`${base}/results`} className="text-[14px] font-semibold text-orange-text">Results <ArrowRight className="inline h-4 w-4" /></Link>}>Last 30 days by channel</SectionTitle>
          {r.by_channel.length === 0 ? <EmptyState tone="d2" title="No results recorded">Add spend, leads and customers by channel to see what's working.</EmptyState> : (
            <ul className="flex flex-col gap-3">{r.by_channel.slice(0, 5).map((c) => {
              const max = Math.max(...r.by_channel.map((x) => x.leads ?? 0), 1);
              return <li key={c.channel}><div className="flex justify-between text-[14px]"><span className="font-semibold">{channelLabel(c.channel)}</span>
                <span className="font-mono text-muted">{c.leads ?? "–"} leads · {money(c.spend, cur)}</span></div>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-sunken"><div className="h-full rounded-full bg-d2" style={{ width: `${((c.leads ?? 0) / max) * 100}%` }} /></div></li>;
            })}</ul>)}
          <p className="mt-3 text-[12px] text-muted">From figures your team recorded. Nothing is pulled from ad accounts.</p>
        </Card>
      </div>
      {data.campaigns.length > 0 && <Card>
        <SectionTitle right={<Link href={`${base}/campaigns`} className="text-[14px] font-semibold text-orange-text">Campaigns <ArrowRight className="inline h-4 w-4" /></Link>}>Campaigns</SectionTitle>
        <ul className="divide-y divide-line">{data.campaigns.map((c) => <li key={c.id} className="flex items-center justify-between gap-2 py-2.5">
          <span className="font-semibold">{c.name}</span><span className="flex items-center gap-2 text-[13px] text-muted">{c.start_date ? `${fmtDate(c.start_date)} – ${fmtDate(c.end_date!)}` : ""}<StatusBadge status={c.status} /></span></li>)}</ul>
      </Card>}
      <p className="flex items-center gap-1.5 text-[13px] text-muted"><ShieldCheck className="h-4 w-4" />
        {data.plan.ai_unlimited ? `${data.plan.name} plan: unlimited AI until your plan ends.` : `Free plan: ${data.plan.free_remaining} of ${data.plan.free_limit} AI generations left this month.`}</p>
    </div>
  );
}
