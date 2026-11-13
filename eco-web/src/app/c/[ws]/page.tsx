"use client";
import { ArrowRight, CalendarPlus, CheckCircle2, Circle, Sparkles, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useApi } from "@/lib/api";
import type { Asset, CalendarItem, Campaign } from "@/lib/types";
import { platformLabel } from "@/lib/types";
import { useWs } from "@/components/Shell";
import { Card, EmptyState, Notice, SectionTitle, Skeleton, Stat, StatusBadge, fmtDate, fmtTime } from "@/components/ui";

type Overview = {
  client: { name: string; platforms: string[]; profile_complete: number };
  content: Record<string, number>;
  calendar: { upcoming: CalendarItem[]; overdue: number };
  campaigns: Campaign[]; recent: Asset[];
  plan: { code: string; name: string; ai_unlimited: boolean; free_used: number | null; free_limit: number | null; free_remaining: number | null };
  checklist: { key: string; label: string; done: boolean }[];
};
const CHECK_LINKS: Record<string, string> = { profile: "/brand", brand_voice: "/brand", first_draft: "/studio",
  calendar: "/calendar", approval: "/approvals", metrics: "/reports" };

export default function Dashboard() {
  const { ws, base } = useWs();
  const { data, error } = useApi<Overview>(`/v1/workspaces/${ws.id}/creator/overview`);
  if (error) return <Notice tone="danger">Couldn't load the dashboard. Refresh to try again.</Notice>;
  if (!data) return <div className="flex flex-col gap-4"><Skeleton className="h-36" /><div className="grid gap-4 sm:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}</div></div>;
  const doneCount = data.checklist.filter((c) => c.done).length;
  const hour = new Date().getHours();
  return (
    <div className="flex flex-col gap-8">
      <section className="relative overflow-hidden rounded-l bg-d1 p-6 text-on-division sm:p-8">
        <div className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-orange/30 blur-3xl" aria-hidden />
        <div className="relative">
          <div className="text-[12px] font-semibold uppercase tracking-[0.6px]">{hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening"}</div>
          <h1 className="mt-1 font-display text-[32px] font-bold leading-[38px] tracking-[-0.5px] sm:text-[40px] sm:leading-[44px]">{data.client.name}</h1>
          <p className="mt-2 max-w-[60ch] opacity-90">
            {data.client.platforms.length ? data.client.platforms.map(platformLabel).join(" · ") : "Add platforms in Brand & audience"}
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <Link href={`${base}/studio`} className="inline-flex min-h-[40px] items-center gap-2 rounded-m bg-orange px-4 text-[14px] font-semibold text-on-orange transition hover:brightness-95">
              <Sparkles className="h-4 w-4" />Create content</Link>
            <Link href={`${base}/calendar`} className="inline-flex min-h-[40px] items-center gap-2 rounded-m border border-cream/60 bg-black/20 px-4 text-[14px] font-semibold hover:bg-black/30">
              <CalendarPlus className="h-4 w-4" />Plan calendar</Link>
            <Link href={`${base}/reports`} className="inline-flex min-h-[40px] items-center gap-2 rounded-m border border-cream/60 bg-black/20 px-4 text-[14px] font-semibold hover:bg-black/30">
              <TrendingUp className="h-4 w-4" />Record results</Link>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Drafts" value={data.content.draft} />
        <Stat label="In review" value={data.content.in_review} hint={data.content.in_review ? "Waiting for approval" : undefined} />
        <Stat label="Approved" value={data.content.approved} hint="Ready for you to post" />
        <Stat label="Posted" value={data.content.posted} hint="Marked as posted by your team" />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <SectionTitle right={<Link href={`${base}/calendar`} className="text-[14px] font-semibold text-orange-text">Calendar <ArrowRight className="inline h-4 w-4" /></Link>}>Next 7 days</SectionTitle>
          {data.calendar.overdue > 0 && <div className="mb-3"><Notice tone="warning">{data.calendar.overdue} planned post(s) are past their date and not marked as posted.</Notice></div>}
          {data.calendar.upcoming.length === 0 ? (
            <EmptyState title="Nothing scheduled this week" action={<Link href={`${base}/calendar`} className="font-semibold text-orange-text underline">Plan the calendar</Link>} />
          ) : (
            <ul className="divide-y divide-line">
              {data.calendar.upcoming.map((i) => (
                <li key={i.id} className="flex items-center gap-3 py-2.5">
                  <div className="w-16 shrink-0 font-mono text-[13px] text-muted">{fmtDate(i.scheduled_for, { weekday: "short", day: "numeric" })}<br />{fmtTime(i.scheduled_for)}</div>
                  <div className="min-w-0 flex-1"><div className="truncate font-semibold">{i.title}</div>
                    <div className="text-[13px] text-muted">{platformLabel(i.platform)} · {i.format}</div></div>
                  <StatusBadge status={i.status} />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <SectionTitle right={<span className="font-mono text-[13px] text-muted">{doneCount}/{data.checklist.length}</span>}>Getting set up</SectionTitle>
          <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-sunken"><div className="h-full bg-orange transition-all" style={{ width: `${(doneCount / data.checklist.length) * 100}%` }} /></div>
          <ul className="flex flex-col">
            {data.checklist.map((c) => (
              <li key={c.key}><Link href={base + CHECK_LINKS[c.key]} className="flex min-h-[40px] items-center gap-3 rounded-s px-1 hover:bg-sunken">
                {c.done ? <CheckCircle2 className="h-5 w-5 text-success" aria-label="Done" /> : <Circle className="h-5 w-5 text-control" aria-label="To do" />}
                <span className={c.done ? "text-muted line-through" : ""}>{c.label}</span></Link></li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <SectionTitle right={<Link href={`${base}/library`} className="text-[14px] font-semibold text-orange-text">Library <ArrowRight className="inline h-4 w-4" /></Link>}>Recent content</SectionTitle>
          {data.recent.length === 0 ? <EmptyState title="No content yet" action={<Link href={`${base}/studio`} className="font-semibold text-orange-text underline">Draft something in Studio</Link>} /> : (
            <ul className="divide-y divide-line">{data.recent.map((a) => (
              <li key={a.id}><Link href={`${base}/library?open=${a.id}`} className="flex items-center gap-3 py-2.5 hover:underline">
                <span className="min-w-0 flex-1 truncate">{a.title}</span><span className="text-[13px] text-muted">{a.type}</span><StatusBadge status={a.status} /></Link></li>))}
            </ul>
          )}
        </Card>
        <div className="flex flex-col gap-6">
          <Card>
            <SectionTitle>Plan</SectionTitle>
            {data.plan.ai_unlimited ? <p>{data.plan.name}: unlimited AI while your subscription is active.</p> : (
              <>
                <div className="flex items-baseline justify-between"><span>{data.plan.name} plan</span>
                  <span className="font-mono text-[13px]">{data.plan.free_used} / {data.plan.free_limit} this month</span></div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-sunken"><div className="h-full bg-orange" style={{ width: `${Math.min(100, ((data.plan.free_used ?? 0) / (data.plan.free_limit || 1)) * 100)}%` }} /></div>
                <p className="mt-2 text-[13px] text-muted">Paid plans have no monthly limit.</p>
              </>
            )}
          </Card>
          <Card>
            <SectionTitle>Active campaigns</SectionTitle>
            {data.campaigns.length === 0 ? <p className="text-muted">None yet. <Link href={`${base}/campaigns`} className="font-semibold text-orange-text underline">Plan one</Link></p> : (
              <ul className="flex flex-col gap-2">{data.campaigns.map((c) => (
                <li key={c.id}><Link href={`${base}/campaigns/${c.id}`} className="flex items-center justify-between gap-2 hover:underline">
                  <span className="truncate">{c.name}</span><StatusBadge status={c.status} /></Link></li>))}</ul>
            )}
          </Card>
        </div>
      </div>
      <Notice tone="info" title="Publishing and analytics">
        Platform integrations aren't connected, so nothing is posted or measured automatically. Post approved content
        yourself, mark it as posted in the calendar, and record results in Reports.
      </Notice>
    </div>
  );
}
