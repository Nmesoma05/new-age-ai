"use client";
import { ExternalLink } from "lucide-react";
import { useState } from "react";
import { errorText, post, useApi } from "@/lib/api";
import type { Reference } from "@/lib/fl";
import { Badge, Button, Card, Field, Input, Notice, PageHeader, SectionTitle, Select, Skeleton, Tabs } from "@/components/ui";

function RateFloor({ currencies }: { currencies: string[] }) {
  const [f, setF] = useState({ income: "", hours: "30", costs: "0", share: "60", tax: "0", cur: "USD" });
  const [r, setR] = useState<{ hourly_floor: number; daily_floor: number; billable_hours_per_month: number } | null>(null);
  const [err, setErr] = useState("");
  return (
    <Card>
      <SectionTitle>Minimum rate calculator</SectionTitle>
      <p className="-mt-2 mb-4 text-[14px] text-muted">From your own numbers, not market rates. Use it as a floor, then price on the value you deliver.</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-6">
        <Field label="Monthly income goal" htmlFor="ri"><Input id="ri" type="number" min={0} value={f.income} onChange={(e) => setF({ ...f, income: e.target.value })} /></Field>
        <Field label="Currency" htmlFor="rc"><Select id="rc" value={f.cur} onChange={(e) => setF({ ...f, cur: e.target.value })}>{currencies.map((c) => <option key={c}>{c}</option>)}</Select></Field>
        <Field label="Hours / week" htmlFor="rh"><Input id="rh" type="number" min={1} value={f.hours} onChange={(e) => setF({ ...f, hours: e.target.value })} /></Field>
        <Field label="Monthly costs" htmlFor="rk"><Input id="rk" type="number" min={0} value={f.costs} onChange={(e) => setF({ ...f, costs: e.target.value })} /></Field>
        <Field label="% billable" htmlFor="rs" hint="Time actually paid"><Input id="rs" type="number" min={1} max={100} value={f.share} onChange={(e) => setF({ ...f, share: e.target.value })} /></Field>
        <Field label="% tax to set aside" htmlFor="rt"><Input id="rt" type="number" min={0} max={89} value={f.tax} onChange={(e) => setF({ ...f, tax: e.target.value })} /></Field>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-4">
        <Button disabled={!(Number(f.income) > 0 && Number(f.hours) > 0)} onClick={async () => {
          setErr("");
          try { setR(await post("/v1/freelancer/rate-floor", { income_goal_monthly: Number(f.income), hours_per_week: Number(f.hours),
            monthly_costs: Number(f.costs || 0), billable_share: Number(f.share) / 100, tax_pct: Number(f.tax || 0) })); }
          catch (e) { setErr(errorText(e)); }
        }}>Calculate</Button>
        {r && <p className="text-[15px]">At least <span className="font-mono text-[20px] font-semibold">{f.cur} {r.hourly_floor}</span> an hour ({f.cur} {r.daily_floor} a day), over about {r.billable_hours_per_month} paid hours a month.</p>}
      </div>
      {err && <p className="mt-2 text-[14px] text-danger">{err}</p>}
    </Card>
  );
}

export default function Resources() {
  const rd = useApi<Reference>("/v1/freelancer/reference");
  const [tab, setTab] = useState<"where" | "conventions" | "rates">("where");
  if (!rd.data) return <Skeleton className="h-96" />;
  const r = rd.data;
  const cats = Object.entries(r.resources.categories);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Resources" description="Where to look for work, how to get paid across borders, application norms by country, and a rate calculator." />
      <Tabs value={tab} onChange={setTab} items={[{ id: "where", label: "Where to look & get paid" }, { id: "conventions", label: "CV norms by country" }, { id: "rates", label: "Rate calculator" }]} />
      {tab === "where" && <>
        <Notice title={`Checked on ${r.resources.checked_on}`}>{r.resources.note} No live job feed is connected: search these sites yourself, then add roles to Opportunities to check eligibility, time zones and red flags.</Notice>
        {cats.map(([key, label]) => (
          <section key={key}><h2 className="mb-3 text-[12px] font-semibold uppercase tracking-[0.6px] text-muted">{label}</h2>
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{r.resources.items.filter((x) => x.category === key).map((x) => (
              <li key={x.url} className="flex flex-col gap-1 rounded-m border border-line bg-raised p-4">
                <a href={x.url} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-1 font-semibold hover:underline">{x.name}<ExternalLink className="h-3.5 w-3.5" /></a>
                <p className="flex-1 text-[14px]">{x.note}</p>
                <div className="flex flex-wrap items-center gap-1.5">{x.regions.map((g) => <Badge key={g} tone={g === "africa" ? "d3" : "neutral"}>{g}</Badge>)}
                  <a href={x.source_url} target="_blank" rel="noopener noreferrer nofollow" className="text-[12px] text-muted underline">source</a></div>
              </li>))}</ul></section>))}
      </>}
      {tab === "conventions" && <>
        <Notice>{r.conventions_note}</Notice>
        <div className="overflow-x-auto rounded-m border border-line bg-raised"><table className="w-full min-w-[760px] text-[14px]">
          <thead className="bg-sunken text-left text-[13px]"><tr>{["Market", "Document", "Length", "Photo", "Personal details", "Format"].map((h) => <th key={h} className="p-3">{h}</th>)}</tr></thead>
          <tbody>{r.conventions.map((c) => <tr key={c.key} className="border-t border-line align-top"><td className="p-3 font-semibold">{c.label}</td><td className="p-3">{c.document}</td>
            <td className="p-3">{c.length}</td><td className="p-3">{c.photo}</td><td className="p-3">{c.personal_details}</td><td className="p-3">{c.format}<div className="mt-1 text-muted">{c.notes}</div></td></tr>)}</tbody>
        </table></div>
      </>}
      {tab === "rates" && <RateFloor currencies={r.currencies} />}
    </div>
  );
}
