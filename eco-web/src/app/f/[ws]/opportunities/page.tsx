"use client";
import { AlertTriangle, CheckCircle2, Clock, Compass, ExternalLink, Plus, ShieldQuestion } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { del, errorText, patch, post, useApi } from "@/lib/api";
import { OPP_KINDS, REMOTE_TYPES, payText, type Opportunity, type Reference } from "@/lib/fl";
import type { Exchange } from "@/lib/types";
import { FlToolResult, Working } from "@/components/fl/tools";
import { FxLine, RemotiveFinder, useHomeCurrency } from "@/components/fl/external";
import { flTool } from "@/lib/fl";
import { useWs } from "@/components/Shell";
import { Badge, Button, ConfirmButton, Drawer, EmptyState, Field, Input, LinkButton, Modal, Notice, PageHeader, Select, Skeleton,
  StatusBadge, Tabs, Textarea, cx, fmtDate, useToast } from "@/components/ui";

function Checks({ o, compact }: { o: Opportunity; compact?: boolean }) {
  const c = o.checks;
  return (
    <div className={cx("flex flex-wrap gap-1.5", compact ? "" : "mt-1")}>
      <StatusBadge status={o.status} /><StatusBadge status={c.eligibility.status} />
      {c.timezone && <Badge tone={c.timezone.overlap_hours >= 4 ? "success" : c.timezone.overlap_hours >= 2 ? "warning" : "danger"}>
        <Clock className="mr-1 inline h-3 w-3" />{c.timezone.overlap_hours}h overlap</Badge>}
      {c.risk_signals.length > 0 && <Badge tone="danger"><AlertTriangle className="mr-1 inline h-3 w-3" />{c.risk_signals.length} red flag{c.risk_signals.length > 1 ? "s" : ""}</Badge>}
    </div>
  );
}

function AddModal({ open, onClose, onAdded }: { open: boolean; onClose: () => void; onAdded: (o: Opportunity) => void }) {
  const { ws } = useWs();
  const toast = useToast();
  const rd = useApi<Reference>(open ? "/v1/freelancer/reference" : null);
  const blank = { kind: "job", title: "", organisation: "", url: "", source_name: "", remote_type: "unknown", eligible: "", excluded: "",
    tz: "", start_hour: "9", end_hour: "17", pay_min: "", pay_max: "", pay_currency: "", pay_period: "unknown", deadline: "", description: "" };
  const [f, setF] = useState(blank);
  const [busy, setBusy] = useState(false);
  const zones = Array.from(new Set(rd.data?.countries.map((c) => c.timezone) ?? [])).sort();
  const urlOk = !f.url || /^https?:\/\/\S+$/.test(f.url);
  const set = (k: keyof typeof blank) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal open={open} onClose={onClose} title="Add an opportunity" wide
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={busy} disabled={!f.title.trim() || !urlOk || ((!!f.pay_min || !!f.pay_max) && !f.pay_currency)} onClick={async () => {
        setBusy(true);
        const codes = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
        try {
          const o = await post<Opportunity>(`/v1/workspaces/${ws.id}/freelancer/opportunities`, {
            kind: f.kind, title: f.title.trim(), organisation: f.organisation, url: f.url || null, source_name: f.source_name,
            remote_type: f.remote_type, eligible_countries: codes(f.eligible), excluded_countries: codes(f.excluded),
            timezone_requirement: f.tz ? { tz: f.tz, start_hour: Number(f.start_hour), end_hour: Number(f.end_hour) } : null,
            pay_min: f.pay_min || null, pay_max: f.pay_max || null, pay_currency: f.pay_currency || null, pay_period: f.pay_period,
            deadline: f.deadline || null, description: f.description });
          toast("Saved. Verify it at the source before applying."); setF(blank); onAdded(o);
        } catch (e) { toast(errorText(e), "danger"); } finally { setBusy(false); }
      }}>Save opportunity</Button></>}>
      <div className="flex flex-col gap-4">
        <Notice>Paste what the listing says. The app can't see job boards, so it relies on what you enter, and marks it unverified until you've checked the original posting.</Notice>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Role or project" htmlFor="ot"><Input id="ot" value={f.title} onChange={set("title")} /></Field>
          <Field label="Company or client" htmlFor="oo"><Input id="oo" value={f.organisation} onChange={set("organisation")} /></Field>
          <Field label="Link to the posting" htmlFor="ou" error={urlOk ? undefined : "Use a full https:// link"}><Input id="ou" value={f.url} onChange={set("url")} placeholder="https://" /></Field>
          <Field label="Where you found it" htmlFor="os"><Input id="os" value={f.source_name} onChange={set("source_name")} placeholder="e.g. LinkedIn, a friend" /></Field>
          <Field label="Type" htmlFor="ok"><Select id="ok" value={f.kind} onChange={set("kind")}>{Object.entries(OPP_KINDS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
          <Field label="Remote?" htmlFor="or"><Select id="or" value={f.remote_type} onChange={set("remote_type")}>{Object.entries(REMOTE_TYPES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
          <Field label="Who can apply (as the listing says)" htmlFor="oe" hint="Country codes or regions: NG, KE, EMEA, AFRICA, WORLDWIDE"><Input id="oe" value={f.eligible} onChange={set("eligible")} /></Field>
          <Field label="Excluded countries (if stated)" htmlFor="ox"><Input id="ox" value={f.excluded} onChange={set("excluded")} /></Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-[2fr_1fr_1fr]">
          <Field label="Working hours required in (time zone)" htmlFor="oz"><Select id="oz" value={f.tz} onChange={set("tz")}><option value="">Not stated</option>{zones.map((z) => <option key={z} value={z}>{z.replace(/_/g, " ")}</option>)}</Select></Field>
          <Field label="From" htmlFor="osh"><Select id="osh" value={f.start_hour} disabled={!f.tz} onChange={set("start_hour")}>{Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}</Select></Field>
          <Field label="To" htmlFor="oeh"><Select id="oeh" value={f.end_hour} disabled={!f.tz} onChange={set("end_hour")}>{Array.from({ length: 24 }, (_, h) => h + 1).map((h) => <option key={h} value={h}>{String(h % 24).padStart(2, "0")}:00</option>)}</Select></Field>
        </div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Field label="Pay from" htmlFor="opn"><Input id="opn" type="number" min={0} value={f.pay_min} onChange={set("pay_min")} /></Field>
          <Field label="Pay to" htmlFor="opx"><Input id="opx" type="number" min={0} value={f.pay_max} onChange={set("pay_max")} /></Field>
          <Field label="Currency" htmlFor="opc"><Select id="opc" value={f.pay_currency} onChange={set("pay_currency")}><option value="">–</option>{rd.data?.currencies.map((c) => <option key={c} value={c}>{c}</option>)}</Select></Field>
          <Field label="Per" htmlFor="opp"><Select id="opp" value={f.pay_period} onChange={set("pay_period")}>{["unknown", "hour", "day", "week", "month", "year", "project"].map((x) => <option key={x} value={x}>{x === "unknown" ? "–" : x}</option>)}</Select></Field>
        </div>
        <Field label="Deadline (if any)" htmlFor="od"><Input id="od" type="date" value={f.deadline} onChange={set("deadline")} /></Field>
        <Field label="Paste the description" htmlFor="ods" hint="Used for fit and red-flag checks. Treated as outside information."><Textarea id="ods" rows={6} maxLength={20000} value={f.description} onChange={set("description")} /></Field>
      </div>
    </Modal>
  );
}

function Detail({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const { ws, base, canWrite } = useWs();
  const toast = useToast();
  const o = useApi<Opportunity>(`/v1/workspaces/${ws.id}/freelancer/opportunities/${id}`);
  const [ex, setEx] = useState<Exchange | null>(null);
  const [busy, setBusy] = useState("");
  const d = o.data;
  const act = async (label: string, fn: () => Promise<unknown>, msg?: string) => {
    setBusy(label);
    try { await fn(); if (msg) toast(msg); o.reload(); onChanged(); } catch (e) { toast(errorText(e), "danger"); } finally { setBusy(""); }
  };
  const home = useHomeCurrency();
  return (
    <Drawer open onClose={onClose} title={d?.title ?? "Opportunity"}
      footer={d && canWrite && <div className="flex w-full flex-wrap gap-2">
        <Button loading={busy === "track"} onClick={() => act("track", async () => {
          const a = await post<{ id: string }>(`/v1/workspaces/${ws.id}/freelancer/opportunities/${id}/track`);
          location.href = `${base}/applications?open=${a.id}`;
        })}>Track application</Button>
        <LinkButton href={`${base}/tools/cv?opportunity=${id}`}>Tailor CV</LinkButton>
        <LinkButton href={`${base}/tools/proposal?opportunity=${id}`}>Write letter</LinkButton>
        <span className="flex-1" />
        <ConfirmButton label="Delete this?" onConfirm={async () => { await del(`/v1/workspaces/${ws.id}/freelancer/opportunities/${id}`); toast("Deleted"); onChanged(); onClose(); }}>Delete</ConfirmButton>
      </div>}>
      {!d ? <Skeleton className="h-64" /> : (
        <div className="flex flex-col gap-5">
          <div><div className="text-[14px] text-muted">{d.organisation || "Organisation not given"} · {OPP_KINDS[d.kind as keyof typeof OPP_KINDS]} · {REMOTE_TYPES[d.remote_type as keyof typeof REMOTE_TYPES]}</div>
            <Checks o={d} /></div>
          {d.url && <a href={d.url} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-1 font-semibold text-orange-text underline">Open the original posting<ExternalLink className="h-4 w-4" /></a>}
          <section className="flex flex-col gap-2 rounded-m border border-line bg-raised p-4">
            <h3 className="flex items-center gap-2 font-semibold"><ShieldQuestion className="h-4 w-4" />Is it real and still open?</h3>
            {d.status === "verified" ? <p className="text-[14px]"><CheckCircle2 className="mr-1 inline h-4 w-4 text-success" />You checked it on {fmtDate(d.verified_at!)}{d.verification_note ? `: ${d.verification_note}` : ""}.</p>
              : <p className="text-[14px] text-muted">{d.source === "integration" && d.verification_note ? <span className="mb-1 block text-ink">{d.verification_note}</span> : null}Open the original posting (ideally on the company's own site) and confirm it's still accepting applications. The app can't check for you.</p>}
            {canWrite && d.status !== "verified" && <div className="flex flex-wrap gap-2">
              <Button size="sm" loading={busy === "v"} onClick={() => act("v", () => post(`/v1/workspaces/${ws.id}/freelancer/opportunities/${id}/verify`, { still_open: true, note: "Checked at the source" }), "Marked as verified")}>I checked: still open</Button>
              <Button size="sm" variant="secondary" loading={busy === "c"} onClick={() => act("c", () => post(`/v1/workspaces/${ws.id}/freelancer/opportunities/${id}/verify`, { still_open: false }), "Marked as closed")}>It's closed</Button></div>}
          </section>
          <dl className="grid gap-3 text-[14px] sm:grid-cols-2">
            <div><dt className="text-muted">Eligibility</dt><dd>{d.checks.eligibility.reasons.join(" ")}</dd></div>
            <div><dt className="text-muted">Time zone</dt><dd>{d.checks.timezone ? `Required hours are ${d.checks.timezone.required_window_local}; about ${d.checks.timezone.overlap_hours} hours overlap with ${d.checks.timezone.your_hours}.` : "Not stated, or add your time zone to your profile."}</dd></div>
            <div><dt className="text-muted">Pay</dt><dd>{payText(d)}<FxLine o={d} to={home} />{d.checks.pay_note ? <span className="block text-[12px] text-muted">{d.checks.pay_note}</span> : null}</dd></div>
            <div><dt className="text-muted">Deadline</dt><dd>{d.deadline ? fmtDate(d.deadline, { day: "numeric", month: "short", year: "numeric" }) : "Not stated"}</dd></div>
          </dl>
          {d.checks.risk_signals.length > 0 && <Notice tone="danger" title="Red flags in this listing"><ul className="list-disc pl-5">{d.checks.risk_signals.map((r) => <li key={r.signal}>{r.explanation}</li>)}</ul></Notice>}
          {d.description && <section><h3 className="mb-1 font-semibold">What the listing says</h3>
            <p className="max-h-60 overflow-auto whitespace-pre-wrap rounded-m bg-sunken p-3 text-[14px]">{d.description}</p></section>}
          {canWrite && <div><Button ai loading={busy === "ai"} onClick={async () => {
            setBusy("ai"); setEx(null);
            try { setEx(await post<Exchange>(`/v1/workspaces/${ws.id}/freelancer/generate`, { tool: "opportunity", opportunity_id: id })); }
            catch (e) { toast(errorText(e), "danger"); } finally { setBusy(""); }
          }}>Check my fit</Button></div>}
          {busy === "ai" && <Working label="Comparing with your profile…" />}
          {ex && <FlToolResult ex={ex} def={flTool("opportunity")!} />}
          {canWrite && d.status !== "archived" && <div><Button size="sm" variant="ghost" onClick={() => act("a", () => patch(`/v1/workspaces/${ws.id}/freelancer/opportunities/${id}`, { status: "archived" }), "Archived")}>Archive</Button></div>}
        </div>)}
    </Drawer>
  );
}

export default function Opportunities() {
  const { ws, base, canWrite } = useWs();
  const router = useRouter();
  const open = useSearchParams().get("open");
  const [tab, setTab] = useState<"open" | "all">("open");
  const [adding, setAdding] = useState(false);
  const [finding, setFinding] = useState(false);
  const list = useApi<Opportunity[]>(`/v1/workspaces/${ws.id}/freelancer/opportunities`);
  const rows = (list.data ?? []).filter((o) => tab === "all" || ["unverified", "verified"].includes(o.status));
  const setOpen = (id: string | null) => router.replace(id ? `${base}/opportunities?open=${id}` : `${base}/opportunities`);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Opportunities" description="Jobs and gigs you've found. Each is checked against your country, time zone and common scam signs, and stays unverified until you confirm it at the source.">
        <LinkButton href={`${base}/resources`}>Where to look</LinkButton>
        <Button variant="secondary" icon={<Compass className="h-4 w-4" />} onClick={() => setFinding(true)}>Find on Remotive</Button>
        {canWrite && <Button icon={<Plus className="h-4 w-4" />} onClick={() => setAdding(true)}>Add opportunity</Button>}
      </PageHeader>
      <Tabs value={tab} onChange={setTab} items={[{ id: "open", label: "Open" }, { id: "all", label: "All" }]} />
      {!list.data && <Skeleton className="h-40" />}
      {list.data && rows.length === 0 && <EmptyState tone="d3" icon={<Compass className="h-6 w-6" />} title="No opportunities yet"
        action={<Link className="font-semibold text-orange-text underline" href={`${base}/resources`}>See job boards and marketplaces</Link>}>
        Search Remotive's remote-job feed, or add roles you find anywhere else. We'll check eligibility, time zones and red flags.</EmptyState>}
      <ul className="grid gap-3 md:grid-cols-2">
        {rows.map((o) => (
          <li key={o.id}><button onClick={() => setOpen(o.id)} className="flex w-full flex-col gap-2 rounded-m border border-line bg-raised p-4 text-left transition hover:border-control hover:shadow-1">
            <div className="flex items-start justify-between gap-2"><span className="font-semibold">{o.title}</span>
              {o.deadline && <span className={cx("shrink-0 text-[12px] font-semibold", o.checks.deadline_passed ? "text-danger" : "text-muted")}>Due {fmtDate(o.deadline)}</span>}</div>
            <span className="text-[13px] text-muted">{o.organisation || "Organisation not given"} · {payText(o)}</span>
            <Checks o={o} compact />
          </button></li>))}
      </ul>
      <RemotiveFinder open={finding} onClose={() => setFinding(false)} onImported={(id) => { setFinding(false); list.reload(); setOpen(id); }} />
      <AddModal open={adding} onClose={() => setAdding(false)} onAdded={(o) => { setAdding(false); list.reload(); setOpen(o.id); }} />
      {open && <Detail id={open} onClose={() => setOpen(null)} onChanged={list.reload} />}
    </div>
  );
}
