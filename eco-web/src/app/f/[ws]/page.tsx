"use client";
import { ArrowRight, CalendarClock, Clock, Compass, MapPin, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useApi } from "@/lib/api";
import { ASSET_LABEL } from "@/lib/fl";
import type { Asset } from "@/lib/types";
import { useWs } from "@/components/Shell";
import { Card, EmptyState, Notice, SectionTitle, Skeleton, Stat, cx, fmtDate } from "@/components/ui";

type Overview = {
  profile: null | { full_name: string | null; headline: string | null; career_stage: string; stage_label: string;
    country_name: string | null; city: string | null; timezone: string | null; currency: string | null; completeness: number;
    missing: string[]; has_assessment: boolean; strengths: string[] };
  next_steps: { tool: string; title: string; why: string }[]; saved: Record<string, number>;
  opportunities: Record<string, number>; applications: Record<string, number>;
  counts: { opportunities: number; unverified: number; interviewing: number; follow_ups_due: number };
  follow_ups: { id: string; title: string; organisation: string; next_step: string; due: string; overdue: boolean }[];
  recent: Asset[]; plan: { name: string; ai_unlimited: boolean; free_remaining: number | null; free_limit: number | null };
};
const HREF: Record<string, string> = { profile: "/profile", assessment: "/tools/assessment", applications: "/applications",
  interview: "/interview", opportunities: "/opportunities" };

function LocalTime({ tz }: { tz: string }) {
  const [now, setNow] = useState<string>("");
  useEffect(() => {
    const f = () => { try { setNow(new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: tz }).format(new Date())); } catch { setNow(""); } };
    f(); const t = setInterval(f, 30000); return () => clearInterval(t);
  }, [tz]);
  return now ? <span className="inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5" />{now} your time</span> : null;
}

export default function FlDashboard() {
  const { ws, base } = useWs();
  const { data, error } = useApi<Overview>(`/v1/workspaces/${ws.id}/freelancer/overview`);
  if (error) return <Notice tone="danger">Couldn't load your dashboard. Refresh to try again.</Notice>;
  if (!data) return <div className="flex flex-col gap-4"><Skeleton className="h-40" /><Skeleton className="h-24" /></div>;
  const p = data.profile;
  const active = ["preparing", "applied", "interviewing", "offer"].reduce((n, s) => n + (data.applications[s] ?? 0), 0);
  const saved = Object.values(data.saved).reduce((a, n) => a + n, 0);
  return (
    <div className="flex flex-col gap-8">
      <section className="relative overflow-hidden rounded-l bg-d3 p-6 text-on-division sm:p-8">
        <div className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full bg-orange/30 blur-3xl" aria-hidden />
        <div className="relative">
          <div className="text-[12px] font-semibold uppercase tracking-[0.6px]">{p?.stage_label}</div>
          <h1 className="mt-1 font-display text-[32px] font-bold leading-[38px] tracking-[-0.5px] sm:text-[40px] sm:leading-[44px]">{p?.full_name || "Your career"}</h1>
          <p className="mt-1 text-[17px] opacity-95">{p?.headline || "Add a headline to your profile"}</p>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[14px] opacity-90">
            {(p?.city || p?.country_name) && <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5" />{[p?.city, p?.country_name].filter(Boolean).join(", ")}</span>}
            {p?.timezone && <LocalTime tz={p.timezone} />}
            {p?.currency && <span>Prices in {p.currency}</span>}
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            <Link href={`${base}/opportunities`} className="inline-flex min-h-[40px] items-center gap-2 rounded-m bg-orange px-4 text-[14px] font-semibold text-on-orange hover:brightness-95"><Compass className="h-4 w-4" />Opportunities</Link>
            <Link href={`${base}/tools/cv`} className="inline-flex min-h-[40px] items-center gap-2 rounded-m border border-cream/60 bg-black/20 px-4 text-[14px] font-semibold hover:bg-black/30">CV & resume</Link>
            <Link href={`${base}/tools/pricing`} className="inline-flex min-h-[40px] items-center gap-2 rounded-m border border-cream/60 bg-black/20 px-4 text-[14px] font-semibold hover:bg-black/30">Services & pricing</Link>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Profile" value={`${p?.completeness ?? 0}%`} hint={p?.missing.length ? `Missing: ${p.missing.slice(0, 2).join(", ")}` : "All the basics are in"} />
        <Stat label="Active applications" value={active} hint={data.counts.interviewing ? `${data.counts.interviewing} at interview` : undefined} />
        <Stat label="Opportunities" value={data.counts.opportunities} hint={data.counts.unverified ? `${data.counts.unverified} not verified yet` : undefined} />
        <Stat label="Saved work" value={saved} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <Card>
          <SectionTitle>Recommended next</SectionTitle>
          <p className="-mt-2 mb-3 text-[14px] text-muted">Picked for your stage: {p?.stage_label.toLowerCase()}.</p>
          <ol className="flex flex-col gap-2">{data.next_steps.map((s, i) => (
            <li key={s.tool + i}><Link href={base + (HREF[s.tool] ?? `/tools/${s.tool}`)} className="group flex items-start gap-3 rounded-m border border-line p-3 transition hover:border-control hover:bg-sunken/50">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-d3-soft font-mono text-[13px] font-semibold text-d3">{i + 1}</span>
              <span className="min-w-0 flex-1"><span className="block font-semibold">{s.title}</span><span className="block text-[14px] text-muted">{s.why}</span></span>
              <ArrowRight className="mt-1 h-4 w-4 text-muted group-hover:text-ink" /></Link></li>))}</ol>
        </Card>
        <Card>
          <SectionTitle right={<Link href={`${base}/applications`} className="text-[14px] font-semibold text-orange-text">All <ArrowRight className="inline h-4 w-4" /></Link>}>Follow-ups</SectionTitle>
          {data.follow_ups.length === 0 ? <EmptyState tone="d3" icon={<CalendarClock className="h-6 w-6" />} title="Nothing due">Set a next step on an application to see it here.</EmptyState> : (
            <ul className="flex flex-col gap-2">{data.follow_ups.map((f) => (
              <li key={f.id}><Link href={`${base}/applications?open=${f.id}`} className="flex items-start gap-3 rounded-m p-2 hover:bg-sunken">
                <span className={cx("mt-1 h-2.5 w-2.5 shrink-0 rounded-full", f.overdue ? "bg-danger" : "bg-warning")} aria-hidden />
                <span className="min-w-0 flex-1"><span className="block truncate font-semibold">{f.next_step || "Next step"}</span>
                  <span className="block text-[13px] text-muted">{f.title}{f.organisation ? ` · ${f.organisation}` : ""}</span></span>
                <span className={cx("text-[13px] font-semibold", f.overdue ? "text-danger" : "text-muted")}>{f.overdue ? "Overdue" : fmtDate(f.due)}</span></Link></li>))}</ul>)}
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <SectionTitle right={<Link href={`${base}/profile`} className="text-[14px] font-semibold text-orange-text">Profile <ArrowRight className="inline h-4 w-4" /></Link>}>Your strengths</SectionTitle>
          {p?.has_assessment && p.strengths.length ? <ul className="flex flex-col gap-2">{p.strengths.map((s, i) => <li key={i} className="flex gap-2"><Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-d3" />{s}</li>)}</ul>
            : <EmptyState tone="d3" title="No assessment yet" action={<Link className="font-semibold text-orange-text underline" href={`${base}/tools/assessment`}>Assess my skills</Link>}>See what you can already prove, and what to build next.</EmptyState>}
        </Card>
        <Card>
          <SectionTitle right={<Link href={`${base}/work`} className="text-[14px] font-semibold text-orange-text">All work <ArrowRight className="inline h-4 w-4" /></Link>}>Recent work</SectionTitle>
          {data.recent.length === 0 ? <EmptyState tone="d3" title="Nothing saved yet">Save a CV, letter or plan and it shows up here.</EmptyState> : (
            <ul className="divide-y divide-line">{data.recent.map((a) => <li key={a.id}><Link href={`${base}/work?open=${a.id}`} className="flex items-center gap-3 py-2.5 hover:underline">
              <span className="min-w-0 flex-1 truncate font-semibold">{a.title}</span><span className="text-[13px] text-muted">{ASSET_LABEL[a.type] ?? a.type} · {fmtDate(a.updated_at)}</span></Link></li>)}</ul>)}
        </Card>
      </div>
      <p className="text-[13px] text-muted">{data.plan.ai_unlimited ? `${data.plan.name} plan: unlimited AI until your plan ends.` : `Free plan: ${data.plan.free_remaining} of ${data.plan.free_limit} AI generations left this month.`}</p>
    </div>
  );
}
