"use client";
import { Plus, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { errorText, post, put, useApi } from "@/lib/api";
import { CHANNELS, type BusinessProfile, type Category, type Intelligence, type Stage } from "@/lib/biz";
import type { Exchange } from "@/lib/types";
import { ChannelsEditor, CompetitorsEditor, GoalsEditor, OffersEditor, fromProfile, toBody, type ProfileForm } from "@/components/biz/fields";
import { Thinking } from "@/components/biz/tools";
import { RunPanel } from "@/components/RunPanel";
import { useWs } from "@/components/Shell";
import { Badge, Button, Card, Field, Input, Notice, PageHeader, SectionTitle, Select, Skeleton, StatusBadge, Tabs, Textarea, fmtDate, useToast } from "@/components/ui";

type Cats = { categories: Category[]; stages: Stage[] };
const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);
const EMPTY: Intelligence = { summary: "", stage_assessment: "", positioning_statement: "", value_proposition: "", customer_segments: [],
  competitive_landscape: [], channel_fit: [], priorities: [], risks: [], data_gaps: [] };

function IntelligenceEditor({ value, onSave, disabled }: { value: Intelligence; onSave: (v: Intelligence) => Promise<void>; disabled: boolean }) {
  const [v, setV] = useState<Intelligence>(value);
  const [list, setList] = useState({ priorities: value.priorities.join("\n"), risks: value.risks.join("\n"), data_gaps: value.data_gaps.join("\n") });
  const [busy, setBusy] = useState(false);
  useEffect(() => { setV(value); setList({ priorities: value.priorities.join("\n"), risks: value.risks.join("\n"), data_gaps: value.data_gaps.join("\n") }); }, [value]);
  const t = (k: keyof Intelligence) => (e: React.ChangeEvent<HTMLTextAreaElement>) => setV({ ...v, [k]: e.target.value });
  return (
    <div className="flex flex-col gap-5">
      <Field label="Summary" htmlFor="is"><Textarea id="is" rows={3} maxLength={900} disabled={disabled} value={v.summary} onChange={t("summary")} /></Field>
      <div className="grid gap-4 lg:grid-cols-2">
        <Field label="Where you are" htmlFor="isa"><Textarea id="isa" rows={2} maxLength={500} disabled={disabled} value={v.stage_assessment} onChange={t("stage_assessment")} /></Field>
        <Field label="Positioning" htmlFor="ip"><Textarea id="ip" rows={2} maxLength={400} disabled={disabled} value={v.positioning_statement} onChange={t("positioning_statement")} /></Field>
      </div>
      <Field label="Value proposition" htmlFor="ivp"><Textarea id="ivp" rows={2} maxLength={400} disabled={disabled} value={v.value_proposition} onChange={t("value_proposition")} /></Field>

      <section><h3 className="mb-2 font-semibold">Customer segments</h3>
        <div className="flex flex-col gap-2">{v.customer_segments.map((s, i) => (
          <div key={i} className="grid gap-2 rounded-m border border-line p-3 sm:grid-cols-[1fr_2fr_auto]">
            <Field label="Segment" htmlFor={`sg-${i}`}><Input id={`sg-${i}`} disabled={disabled} value={s.name} onChange={(e) => setV({ ...v, customer_segments: v.customer_segments.map((x, j) => j === i ? { ...x, name: e.target.value } : x) })} /></Field>
            <Field label="Who they are" htmlFor={`sgd-${i}`}><Input id={`sgd-${i}`} disabled={disabled} value={s.description} onChange={(e) => setV({ ...v, customer_segments: v.customer_segments.map((x, j) => j === i ? { ...x, description: e.target.value } : x) })} /></Field>
            {!disabled && <button type="button" aria-label={`Remove segment ${i + 1}`} className="grid h-11 w-11 place-items-center self-end rounded-m text-muted hover:bg-sunken" onClick={() => setV({ ...v, customer_segments: v.customer_segments.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4" /></button>}
          </div>))}
          {!disabled && <div><Button size="sm" variant="secondary" icon={<Plus className="h-4 w-4" />} onClick={() => setV({ ...v, customer_segments: [...v.customer_segments, { name: "", description: "", needs: [], buying_triggers: [], where_to_reach: [] }] })}>Add segment</Button></div>}
        </div></section>

      <section><h3 className="mb-2 font-semibold">Channel fit</h3>
        <div className="flex flex-col gap-2">{v.channel_fit.map((c, i) => (
          <div key={i} className="grid gap-2 rounded-m border border-line p-3 sm:grid-cols-[1fr_140px_2fr_auto]">
            <Field label="Channel" htmlFor={`cf-${i}`}><Select id={`cf-${i}`} disabled={disabled} value={c.channel} onChange={(e) => setV({ ...v, channel_fit: v.channel_fit.map((x, j) => j === i ? { ...x, channel: e.target.value } : x) })}>
              {CHANNELS.map((ch) => <option key={ch.id} value={ch.id}>{ch.label}</option>)}</Select></Field>
            <Field label="Fit" htmlFor={`cff-${i}`}><Select id={`cff-${i}`} disabled={disabled} value={c.fit} onChange={(e) => setV({ ...v, channel_fit: v.channel_fit.map((x, j) => j === i ? { ...x, fit: e.target.value as "strong" } : x) })}>
              <option value="strong">Strong</option><option value="possible">Possible</option><option value="weak">Weak</option></Select></Field>
            <Field label="Why" htmlFor={`cfw-${i}`}><Input id={`cfw-${i}`} disabled={disabled} value={c.why} onChange={(e) => setV({ ...v, channel_fit: v.channel_fit.map((x, j) => j === i ? { ...x, why: e.target.value } : x) })} /></Field>
            {!disabled && <button type="button" aria-label={`Remove channel ${i + 1}`} className="grid h-11 w-11 place-items-center self-end rounded-m text-muted hover:bg-sunken" onClick={() => setV({ ...v, channel_fit: v.channel_fit.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4" /></button>}
          </div>))}
          {!disabled && <div><Button size="sm" variant="secondary" icon={<Plus className="h-4 w-4" />} onClick={() => setV({ ...v, channel_fit: [...v.channel_fit, { channel: "whatsapp", fit: "possible", why: "" }] })}>Add channel</Button></div>}
        </div></section>

      <section><h3 className="mb-2 font-semibold">Competitors</h3>
        {v.competitive_landscape.length === 0 && <p className="text-[14px] text-muted">None in this profile. Competitors you add under Business details are used when you rebuild.</p>}
        <div className="flex flex-col gap-2">{v.competitive_landscape.map((c, i) => (
          <div key={i} className="grid gap-2 rounded-m border border-line p-3 sm:grid-cols-[1fr_2fr_2fr]">
            <div className="self-center font-semibold">{c.competitor}</div>
            <Field label="What we know" htmlFor={`cl-${i}`}><Input id={`cl-${i}`} disabled={disabled} value={c.what_we_know} onChange={(e) => setV({ ...v, competitive_landscape: v.competitive_landscape.map((x, j) => j === i ? { ...x, what_we_know: e.target.value } : x) })} /></Field>
            <Field label="How to stand out" htmlFor={`cls-${i}`}><Input id={`cls-${i}`} disabled={disabled} value={c.how_to_stand_out} onChange={(e) => setV({ ...v, competitive_landscape: v.competitive_landscape.map((x, j) => j === i ? { ...x, how_to_stand_out: e.target.value } : x) })} /></Field>
          </div>))}</div></section>

      <div className="grid gap-4 lg:grid-cols-3">
        <Field label="Priorities (next 90 days)" htmlFor="ipr" hint="One per line"><Textarea id="ipr" rows={4} disabled={disabled} value={list.priorities} onChange={(e) => setList({ ...list, priorities: e.target.value })} /></Field>
        <Field label="Risks" htmlFor="iri" hint="One per line"><Textarea id="iri" rows={4} disabled={disabled} value={list.risks} onChange={(e) => setList({ ...list, risks: e.target.value })} /></Field>
        <Field label="Missing information" htmlFor="idg" hint="Add these to improve the advice"><Textarea id="idg" rows={4} disabled={disabled} value={list.data_gaps} onChange={(e) => setList({ ...list, data_gaps: e.target.value })} /></Field>
      </div>
      {!disabled && <div><Button loading={busy} onClick={async () => {
        setBusy(true);
        try { await onSave({ ...v, priorities: lines(list.priorities), risks: lines(list.risks), data_gaps: lines(list.data_gaps) }); } finally { setBusy(false); }
      }}>Save intelligence profile</Button></div>}
    </div>
  );
}

export default function Profile() {
  const { ws, canWrite } = useWs();
  const toast = useToast();
  const search = useSearchParams();
  const base = `/v1/workspaces/${ws.id}`;
  const prof = useApi<BusinessProfile>(`${base}/business-profile`);
  const cats = useApi<Cats>("/v1/business/categories");
  const [tab, setTab] = useState<"intelligence" | "details" | "brand">("intelligence");
  const [f, setF] = useState<ProfileForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [gen, setGen] = useState<{ busy: boolean; ex: Exchange | null; err: string }>({ busy: false, ex: null, err: "" });
  const auto = useRef(false);
  useEffect(() => { if (prof.data) setF(fromProfile(prof.data)); }, [prof.data]);

  async function build() {
    setGen({ busy: true, ex: null, err: "" });
    try { setGen({ busy: false, ex: await post<Exchange>(`${base}/business/generate`, { tool: "intelligence" }), err: "" }); }
    catch (e) { setGen({ busy: false, ex: null, err: errorText(e) }); }
  }
  useEffect(() => {
    if (search.get("build") === "1" && prof.data && !auto.current && canWrite && !Object.keys(prof.data.intelligence ?? {}).length) {
      auto.current = true; build();
    }
  }, [search, prof.data, canWrite]); // eslint-disable-line react-hooks/exhaustive-deps

  if (prof.error) return <Notice tone="danger">{errorText(prof.error)}</Notice>;
  if (!prof.data || !f) return <Skeleton className="h-96" />;
  const p = prof.data;
  const intel = { ...EMPTY, ...(p.intelligence as Partial<Intelligence>) } as Intelligence;
  const hasIntel = Object.keys(p.intelligence ?? {}).length > 0;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Profile & intelligence" description="Your business facts, and the Marketing Intelligence Profile the AI builds from them. You can edit both.">
        {canWrite && <Button ai loading={gen.busy} onClick={build}>{hasIntel ? "Rebuild with AI" : "Build with AI"}</Button>}
      </PageHeader>
      {gen.err && <Notice tone="danger">{gen.err}</Notice>}
      {gen.busy && <Thinking label="Building your Marketing Intelligence Profile…" />}
      {gen.ex && (
        <Card className="flex flex-col gap-3 border-2 border-d2 animate-rise">
          <div className="flex items-center gap-2 font-semibold"><Sparkles className="h-4 w-4 text-d2" />New profile drafted</div>
          <RunPanel run={gen.ex.run} />
          {gen.ex.run.status === "succeeded" && gen.ex.run.output && <>
            <p className="text-[14px]">{String(gen.ex.run.output.summary)}</p>
            <p className="text-[13px] text-muted">It replaces the current intelligence profile only if you choose to use it.</p>
            <div className="flex gap-2"><Button onClick={async () => {
              try { await post(`${base}/business/runs/${gen.ex!.run.id}/apply-intelligence`); toast("Profile updated"); setGen({ busy: false, ex: null, err: "" }); prof.reload(); setTab("intelligence"); }
              catch (e) { toast(errorText(e), "danger"); }
            }}>Use this profile</Button><Button variant="ghost" onClick={() => setGen({ busy: false, ex: null, err: "" })}>Discard</Button></div></>}
        </Card>)}
      <Tabs value={tab} onChange={setTab} items={[{ id: "intelligence", label: "Intelligence profile" }, { id: "details", label: "Business details" }, { id: "brand", label: "Brand & messaging" }]} />

      {tab === "intelligence" && (
        <Card>
          <SectionTitle right={p.intelligence_updated_at && <span className="text-[13px] text-muted">{intel.edited_by_user ? "Edited" : "AI draft"} · {fmtDate(p.intelligence_updated_at)}</span>}>Marketing Intelligence Profile</SectionTitle>
          {!hasIntel ? <Notice title="Not built yet">Click <span className="font-semibold">Build with AI</span> to turn your business details into a profile you can edit.</Notice>
            : <>
              {intel.uncertainties?.length ? <div className="mb-4"><Notice tone="warning" title="The AI wasn't sure about">{intel.uncertainties.join("; ")}</Notice></div> : null}
              <div className="mb-5 flex flex-wrap gap-2">{intel.channel_fit.map((c) => <span key={c.channel} className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-[13px]">{CHANNELS.find((x) => x.id === c.channel)?.label}<StatusBadge status={c.fit} /></span>)}</div>
              <IntelligenceEditor value={intel} disabled={!canWrite} onSave={async (v) => {
                // Send only the editable sections; provenance fields (source run, AI uncertainties) are kept server-side.
                const { summary, stage_assessment, positioning_statement, value_proposition, customer_segments,
                  competitive_landscape, channel_fit, priorities, risks, data_gaps } = v;
                try { await put(`${base}/business/intelligence`, { summary, stage_assessment, positioning_statement, value_proposition,
                  customer_segments, competitive_landscape, channel_fit, priorities, risks, data_gaps }); toast("Intelligence profile saved"); prof.reload(); } catch (e) { toast(errorText(e), "danger"); }
              }} /></>}
        </Card>)}

      {tab === "details" && (
        <Card className="flex flex-col gap-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Business name" htmlFor="pn"><Input id="pn" disabled={!canWrite} value={f.business_name} onChange={(e) => setF({ ...f, business_name: e.target.value })} /></Field>
            <Field label="Category" htmlFor="pc"><Select id="pc" disabled={!canWrite} value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
              {cats.data?.categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</Select></Field>
            <Field label="Industry" htmlFor="pi"><Input id="pi" disabled={!canWrite} value={f.industry} onChange={(e) => setF({ ...f, industry: e.target.value })} /></Field>
            <Field label="Stage" htmlFor="ps"><Select id="ps" disabled={!canWrite} value={f.stage} onChange={(e) => setF({ ...f, stage: e.target.value })}>
              {cats.data?.stages.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}</Select></Field>
            <Field label="Location" htmlFor="pl"><Input id="pl" disabled={!canWrite} value={f.location} onChange={(e) => setF({ ...f, location: e.target.value })} /></Field>
            <Field label="Target markets" htmlFor="pt" hint="Comma separated"><Input id="pt" disabled={!canWrite} value={f.target_markets} onChange={(e) => setF({ ...f, target_markets: e.target.value })} /></Field>
            <Field label="Sells to" htmlFor="pm"><Select id="pm" disabled={!canWrite} value={f.business_model} onChange={(e) => setF({ ...f, business_model: e.target.value as "b2c" })}>
              <option value="b2c">Consumers (B2C)</option><option value="b2b">Businesses (B2B)</option><option value="both">Both</option></Select></Field>
            <Field label="Website" htmlFor="pw"><Input id="pw" disabled={!canWrite} value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} placeholder="https://" /></Field>
          </div>
          <section><h3 className="mb-2 font-semibold">Products & services</h3><OffersEditor disabled={!canWrite} value={f.offers} onChange={(offers) => setF({ ...f, offers })} /></section>
          <Field label="Ideal customers" htmlFor="pcu"><Textarea id="pcu" disabled={!canWrite} value={f.customers} onChange={(e) => setF({ ...f, customers: e.target.value })} /></Field>
          <Field label="What makes you different" htmlFor="pd"><Textarea id="pd" disabled={!canWrite} value={f.differentiators} onChange={(e) => setF({ ...f, differentiators: e.target.value })} /></Field>
          <section><h3 className="mb-2 font-semibold">Competitors</h3><CompetitorsEditor disabled={!canWrite} value={f.competitors} onChange={(competitors) => setF({ ...f, competitors })} /></section>
          <section><h3 className="mb-2 font-semibold">Channels</h3><ChannelsEditor disabled={!canWrite} value={f.channels} onChange={(channels) => setF({ ...f, channels })} /></section>
          <section><h3 className="mb-2 font-semibold">Goals</h3><GoalsEditor disabled={!canWrite} value={f.goals} onChange={(goals) => setF({ ...f, goals })} /></section>
          <div className="grid gap-4 sm:grid-cols-[1fr_120px_2fr]">
            <Field label="Monthly budget" htmlFor="pb"><Input id="pb" type="number" min={0} disabled={!canWrite} value={f.budget_amount} onChange={(e) => setF({ ...f, budget_amount: e.target.value })} /></Field>
            <Field label="Currency" htmlFor="pbc"><Input id="pbc" maxLength={3} disabled={!canWrite} value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value.toUpperCase() })} /></Field>
            <Field label="Budget notes" htmlFor="pbn"><Input id="pbn" disabled={!canWrite} value={f.budget_notes} onChange={(e) => setF({ ...f, budget_notes: e.target.value })} /></Field>
          </div>
          {canWrite && <div className="sticky bottom-20 z-10 flex justify-end sm:bottom-4"><Button loading={saving} onClick={async () => {
            setSaving(true);
            try { await put(`${base}/business-profile`, toBody(f, p.brand)); toast("Profile saved"); prof.reload(); }
            catch (e) { toast(errorText(e), "danger"); } finally { setSaving(false); }
          }}>Save business details</Button></div>}
        </Card>)}

      {tab === "brand" && (
        <Card className="flex flex-col gap-4">
          <SectionTitle>Brand & messaging</SectionTitle>
          {!Object.keys(p.brand ?? {}).length ? <Notice>Nothing applied yet. Run <Link className="underline" href={`/b/${ws.id}/tools/positioning`}>Positioning & messaging</Link> and apply the parts you like.</Notice> : (
            <dl className="grid gap-4 sm:grid-cols-2">
              {p.brand.positioning_statement && <div><dt className="text-[13px] font-semibold text-muted">Positioning</dt><dd>{p.brand.positioning_statement}</dd></div>}
              {p.brand.value_proposition && <div><dt className="text-[13px] font-semibold text-muted">Value proposition</dt><dd>{p.brand.value_proposition}</dd></div>}
              {p.brand.elevator_pitch && <div className="sm:col-span-2"><dt className="text-[13px] font-semibold text-muted">Elevator pitch</dt><dd>{p.brand.elevator_pitch}</dd></div>}
              {p.brand.taglines && <div><dt className="text-[13px] font-semibold text-muted">Taglines</dt><dd><ul className="list-disc pl-5">{(p.brand.taglines as string[]).map((t) => <li key={t}>{t}</li>)}</ul></dd></div>}
              {p.brand.brand_personality && <div><dt className="text-[13px] font-semibold text-muted">Personality</dt><dd className="flex flex-wrap gap-1">{(p.brand.brand_personality as string[]).map((t) => <Badge key={t} tone="d2">{t}</Badge>)}</dd></div>}
              {p.brand.tone_guidance && <div><dt className="text-[13px] font-semibold text-muted">Tone</dt><dd>{p.brand.tone_guidance}</dd></div>}
              {p.brand.visual_direction && <div><dt className="text-[13px] font-semibold text-muted">Visual direction</dt><dd>{p.brand.visual_direction}</dd></div>}
            </dl>)}
        </Card>)}
    </div>
  );
}
