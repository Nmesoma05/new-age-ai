"use client";
// Studio tools: one form + one result view per AI tool. Pages embed these so every flow behaves the same way.
import { Save, Wand2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { errorText, post, useApi } from "@/lib/api";
import type { Campaign, Exchange, Platform } from "@/lib/types";
import { PLATFORMS, platformLabel } from "@/lib/types";
import { PlatformPicker } from "./PlatformPicker";
import { RunPanel } from "./RunPanel";
import { useWs } from "./Shell";
import { Badge, Button, Card, Field, Input, Markdown, Notice, Select, Skeleton, Textarea, Toggle, cx, useToast } from "./ui";

export type Kind = "content" | "brand_voice" | "calendar" | "campaign" | "research" | "report";

export function useGenerate() {
  const { ws } = useWs();
  const [result, setResult] = useState<Exchange | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run(body: Record<string, unknown>) {
    setBusy(true); setError(""); setResult(null);
    try { setResult(await post<Exchange>(`/v1/workspaces/${ws.id}/creator/generate`, body)); }
    catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }
  return { run, result, busy, error, setResult };
}

export function Generating({ label }: { label: string }) {
  return (
    <Card className="flex flex-col gap-3" aria-busy="true">
      <div className="flex items-center gap-2 text-[14px] font-semibold"><Wand2 className="h-4 w-4 animate-pulse text-d1" />{label}</div>
      <Skeleton className="h-4 w-3/4" /><Skeleton className="h-4 w-2/3" /><Skeleton className="h-24 w-full" />
    </Card>
  );
}

const isoToday = () => new Date().toISOString().slice(0, 10);
const plusDays = (d: string, n: number) => { const x = new Date(d + "T00:00:00Z"); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); };

// ====================================================================== content
type Draft = { platform: Platform; format: string; hook: string; body: string; thread_parts: string[]; hashtags: string[];
  call_to_action: string; visual_idea: string };

export function ContentForm({ onRun, busy, platforms, disabled }: { onRun: (b: Record<string, unknown>) => void; busy: boolean;
  platforms: string[]; disabled?: boolean }) {
  const [brief, setBrief] = useState("");
  const [plats, setPlats] = useState<Platform[]>((platforms.length ? platforms : ["instagram"]) as Platform[]);
  const [count, setCount] = useState(3);
  const [formats, setFormats] = useState<string[]>([]);
  return (
    <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); onRun({ kind: "content", brief, platforms: plats, count, formats }); }}>
      <Field label="What should the content be about?" htmlFor="brief" hint="Topic, offer, angle, anything to include or avoid.">
        <Textarea id="brief" value={brief} onChange={(e) => setBrief(e.target.value)} required minLength={3}
          placeholder="e.g. Launch of our new cold brew. Mention it's only available weekday mornings." /></Field>
      <Field label="Platforms"><PlatformPicker value={plats} onChange={setPlats} /></Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="How many drafts" htmlFor="count"><Select id="count" value={count} onChange={(e) => setCount(+e.target.value)}>
          {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}</Select></Field>
        <Field label="Formats (optional)"><div className="flex flex-wrap gap-2">
          {["post", "thread", "caption", "carousel", "reel_script", "story"].map((f) => (
            <Toggle key={f} on={formats.includes(f)} onChange={(on) => setFormats(on ? [...formats, f] : formats.filter((x) => x !== f))}>
              {f.replace("_", " ")}</Toggle>))}</div></Field>
      </div>
      <div><Button type="submit" ai loading={busy} disabled={disabled || brief.trim().length < 3 || !plats.length}>Generate {count} draft{count > 1 ? "s" : ""}</Button></div>
    </form>
  );
}

export function ContentResults({ ex }: { ex: Exchange }) {
  const { ws, base, canWrite } = useWs();
  const toast = useToast();
  const original = (ex.run.output?.drafts ?? []) as Draft[];
  const [drafts, setDrafts] = useState<Draft[]>(original);
  const [picked, setPicked] = useState<number[]>(original.map((_, i) => i));
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const update = (i: number, patchD: Partial<Draft>) => setDrafts(drafts.map((d, j) => (j === i ? { ...d, ...patchD } : d)));
  const toText = (d: Draft) => [d.hook && `Hook: ${d.hook}`, d.body, ...d.thread_parts.map((p, n) => `${n + 2}/ ${p}`),
    d.hashtags.map((h) => "#" + h.replace(/^#/, "")).join(" "), d.call_to_action && `CTA: ${d.call_to_action}`].filter(Boolean).join("\n\n");

  async function save() {
    setBusy(true);
    try {
      const assets = await post<{ id: string }[]>(`/v1/workspaces/${ws.id}/creator/runs/${ex.run.id}/save-drafts`, { indexes: picked });
      // Any edits made here become version 2, so the AI's original stays in the history.
      await Promise.all(picked.map((di, k) => JSON.stringify(drafts[di]) !== JSON.stringify(original[di])
        ? post(`/v1/workspaces/${ws.id}/assets/${assets[k].id}/versions`, { body: drafts[di], body_text: toText(drafts[di]) })
        : Promise.resolve()));
      setSaved(true);
      toast(`Saved ${assets.length} draft${assets.length > 1 ? "s" : ""} to the library`);
    } catch (e) { toast(errorText(e), "danger"); }
    finally { setBusy(false); }
  }

  return (
    <div className="flex flex-col gap-4">
      <RunPanel run={ex.run} />
      <div className="grid gap-4 lg:grid-cols-2">
        {drafts.map((d, i) => {
          const limit = PLATFORMS.find((p) => p.id === d.platform)?.limit ?? 5000;
          const len = d.body.length + d.hashtags.reduce((n, h) => n + h.length + 2, 0);
          const on = picked.includes(i);
          return (
            <Card key={i} className={cx("flex flex-col gap-3 transition animate-rise", on && "border-orange")}>
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2"><Badge tone="d1">{platformLabel(d.platform)}</Badge><Badge>{d.format.replace("_", " ")}</Badge></div>
                <label className="inline-flex items-center gap-2 text-[13px] font-semibold">
                  <input type="checkbox" className="h-4 w-4 accent-[rgb(var(--orange))]" checked={on} disabled={saved}
                    onChange={(e) => setPicked(e.target.checked ? [...picked, i].sort() : picked.filter((x) => x !== i))} />Keep</label>
              </div>
              <Field label="Hook" htmlFor={`h${i}`}><Input id={`h${i}`} value={d.hook} disabled={saved} onChange={(e) => update(i, { hook: e.target.value })} /></Field>
              <Field label="Post" htmlFor={`b${i}`}>
                <Textarea id={`b${i}`} rows={6} value={d.body} disabled={saved} onChange={(e) => update(i, { body: e.target.value })} />
                <div className={cx("text-right font-mono text-[12px]", len > limit ? "text-danger" : "text-muted")}>{len} / {limit}</div>
              </Field>
              {d.thread_parts.length > 0 && <div className="text-[13px] text-muted">+ {d.thread_parts.length} more post(s) in the thread</div>}
              <Field label="Hashtags" htmlFor={`t${i}`}><Input id={`t${i}`} value={d.hashtags.join(" ")} disabled={saved}
                onChange={(e) => update(i, { hashtags: e.target.value.split(/\s+/).map((x) => x.replace(/^#/, "")).filter(Boolean) })} /></Field>
              <div className="text-[13px]"><span className="font-semibold">CTA:</span> {d.call_to_action}</div>
              <div className="rounded-s bg-sunken p-2 text-[13px] text-muted"><span className="font-semibold text-ink">Visual idea:</span> {d.visual_idea}</div>
            </Card>
          );
        })}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {!saved ? <Button icon={<Save className="h-4 w-4" />} onClick={save} loading={busy} disabled={!canWrite || !picked.length}>
          Save {picked.length} to library</Button>
          : <Link href={`${base}/library`} className="font-semibold text-orange-text underline">Open the library to review and submit for approval</Link>}
        <span className="text-[13px] text-muted">Saved drafts stay editable, with every version kept.</span>
      </div>
    </div>
  );
}

// ====================================================================== brand voice
export function BrandForm({ onRun, busy, disabled }: { onRun: (b: Record<string, unknown>) => void; busy: boolean; disabled?: boolean }) {
  const [brief, setBrief] = useState("Build a brand voice, audience personas and content pillars from what we know about this client.");
  return (
    <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); onRun({ kind: "brand_voice", brief }); }}>
      <Field label="What should the strategist focus on?" htmlFor="bbrief"><Textarea id="bbrief" value={brief} onChange={(e) => setBrief(e.target.value)} /></Field>
      <div><Button type="submit" ai loading={busy} disabled={disabled || brief.trim().length < 3}>Build brand voice</Button></div>
    </form>
  );
}

export function BrandResult({ ex, onApplied }: { ex: Exchange; onApplied?: () => void }) {
  const { ws, canWrite } = useWs();
  const toast = useToast();
  const [parts, setParts] = useState<string[]>(["voice", "pillars"]);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  return (
    <div className="flex flex-col gap-4">
      <RunPanel run={ex.run} />
      <Card><Markdown text={ex.assistant_message.content} /></Card>
      <Card className="flex flex-col gap-3">
        <div className="font-semibold">Apply to the client profile</div>
        <div className="flex flex-wrap gap-2">
          {[["voice", "Voice & words"], ["positioning", "Positioning"], ["personas", "Audience personas"], ["pillars", "Content pillars"]].map(([k, l]) => (
            <Toggle key={k} on={parts.includes(k)} disabled={done} onChange={(on) => setParts(on ? [...parts, k] : parts.filter((x) => x !== k))}>{l}</Toggle>))}
        </div>
        <div><Button disabled={!canWrite || !parts.length || done} loading={busy} onClick={async () => {
          setBusy(true);
          try { await post(`/v1/workspaces/${ws.id}/creator/runs/${ex.run.id}/apply-brand`, { parts }); setDone(true); toast("Applied to the client profile"); onApplied?.(); }
          catch (e) { toast(errorText(e), "danger"); } finally { setBusy(false); }
        }}>{done ? "Applied" : "Apply selected"}</Button></div>
        <p className="text-[13px] text-muted">Only what you select is changed. The previous profile version is kept.</p>
      </Card>
    </div>
  );
}

// ====================================================================== calendar plan
export function CalendarForm({ onRun, busy, platforms, disabled }: { onRun: (b: Record<string, unknown>) => void; busy: boolean;
  platforms: string[]; disabled?: boolean }) {
  const [start, setStart] = useState(isoToday());
  const [end, setEnd] = useState(plusDays(isoToday(), 13));
  const [plats, setPlats] = useState<Platform[]>((platforms.length ? platforms : ["instagram"]) as Platform[]);
  const [brief, setBrief] = useState("A content calendar that builds the brand and drives enquiries.");
  const days = (new Date(end).getTime() - new Date(start).getTime()) / 86400000;
  return (
    <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); onRun({ kind: "calendar", brief, start_date: start, end_date: end, platforms: plats }); }}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="From" htmlFor="cs"><Input id="cs" type="date" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
        <Field label="To" htmlFor="ce" error={days < 0 ? "End before start" : days > 92 ? "Plan up to 3 months at a time" : undefined}>
          <Input id="ce" type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
      </div>
      <Field label="Platforms"><PlatformPicker value={plats} onChange={setPlats} /></Field>
      <Field label="Strategy focus" htmlFor="cb"><Textarea id="cb" value={brief} onChange={(e) => setBrief(e.target.value)} /></Field>
      <div><Button type="submit" ai loading={busy} disabled={disabled || days < 0 || days > 92 || !plats.length}>Plan the calendar</Button></div>
    </form>
  );
}

type Entry = { date: string; time: string; platform: string; format: string; pillar: string; title: string; idea: string };
export function CalendarResult({ ex, onImported }: { ex: Exchange; onImported?: () => void }) {
  const { ws, canWrite } = useWs();
  const toast = useToast();
  const items = (ex.run.output?.items ?? []) as Entry[];
  const [picked, setPicked] = useState<number[]>(items.map((_, i) => i));
  const [campaign, setCampaign] = useState("");
  const camps = useApi<Campaign[]>(`/v1/workspaces/${ws.id}/creator/campaigns`);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const out = ex.run.output ?? {};
  return (
    <div className="flex flex-col gap-4">
      <RunPanel run={ex.run} />
      <Card><div className="font-semibold">Strategy</div><p className="mt-1">{out.strategy_summary}</p>
        <p className="mt-2 text-[14px] text-muted"><span className="font-semibold text-ink">Rhythm:</span> {out.posting_rhythm}</p></Card>
      <div className="overflow-x-auto rounded-m border border-line bg-raised">
        <table className="w-full text-[14px]">
          <thead className="bg-sunken text-left text-[13px]"><tr>
            <th className="p-2"><span className="sr-only">Import</span></th><th className="p-2">When</th><th className="p-2">Platform</th>
            <th className="p-2">Pillar</th><th className="p-2">Post</th></tr></thead>
          <tbody>{items.map((it, i) => (
            <tr key={i} className="border-t border-line align-top">
              <td className="p-2"><input type="checkbox" aria-label={`Import ${it.title}`} className="h-4 w-4 accent-[rgb(var(--orange))]" checked={picked.includes(i)} disabled={done}
                onChange={(e) => setPicked(e.target.checked ? [...picked, i] : picked.filter((x) => x !== i))} /></td>
              <td className="whitespace-nowrap p-2 font-mono text-[13px]">{it.date}<br />{it.time}</td>
              <td className="p-2">{platformLabel(it.platform)}<div className="text-[12px] text-muted">{it.format}</div></td>
              <td className="p-2">{it.pillar}</td>
              <td className="p-2"><div className="font-semibold">{it.title}</div><div className="text-muted">{it.idea}</div></td>
            </tr>))}</tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        {(camps.data?.length ?? 0) > 0 && (
          <Field label="Link to campaign (optional)" htmlFor="lc"><Select id="lc" value={campaign} onChange={(e) => setCampaign(e.target.value)} disabled={done}>
            <option value="">No campaign</option>{camps.data!.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
        )}
        <Button disabled={!canWrite || !picked.length || done} loading={busy} onClick={async () => {
          setBusy(true);
          try {
            await post(`/v1/workspaces/${ws.id}/creator/runs/${ex.run.id}/import-calendar`, { indexes: picked, campaign_id: campaign || undefined });
            setDone(true); toast(`Added ${picked.length} item(s) to the calendar`); onImported?.();
          } catch (e) { toast(errorText(e), "danger"); } finally { setBusy(false); }
        }}>{done ? "Added to calendar" : `Add ${picked.length} to calendar`}</Button>
      </div>
    </div>
  );
}

// ====================================================================== campaign plan
export function CampaignForm({ onRun, busy, platforms, disabled }: { onRun: (b: Record<string, unknown>) => void; busy: boolean;
  platforms: string[]; disabled?: boolean }) {
  const [brief, setBrief] = useState("");
  const [start, setStart] = useState(plusDays(isoToday(), 7));
  const [end, setEnd] = useState(plusDays(isoToday(), 37));
  const [plats, setPlats] = useState<Platform[]>((platforms.length ? platforms : ["instagram"]) as Platform[]);
  return (
    <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); onRun({ kind: "campaign", brief, start_date: start, end_date: end, platforms: plats }); }}>
      <Field label="What's the campaign for?" htmlFor="kb" hint="Product, offer, event or goal.">
        <Textarea id="kb" value={brief} onChange={(e) => setBrief(e.target.value)} placeholder="e.g. Launch our December gift boxes" /></Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Starts" htmlFor="ks"><Input id="ks" type="date" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
        <Field label="Ends" htmlFor="ke"><Input id="ke" type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
      </div>
      <Field label="Channels"><PlatformPicker value={plats} onChange={setPlats} /></Field>
      <div><Button type="submit" ai loading={busy} disabled={disabled || brief.trim().length < 3 || end < start || !plats.length}>Plan the campaign</Button></div>
    </form>
  );
}

export function CampaignResult({ ex, onCreated }: { ex: Exchange; onCreated?: (id: string) => void }) {
  const { ws, canWrite } = useWs();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex flex-col gap-4">
      <RunPanel run={ex.run} />
      <Card><Markdown text={ex.assistant_message.content} /></Card>
      <div><Button disabled={!canWrite} loading={busy} onClick={async () => {
        setBusy(true);
        try { const c = await post<{ id: string }>(`/v1/workspaces/${ws.id}/creator/runs/${ex.run.id}/create-campaign`); toast("Campaign created"); onCreated?.(c.id); }
        catch (e) { toast(errorText(e), "danger"); } finally { setBusy(false); }
      }}>Create campaign from this plan</Button></div>
    </div>
  );
}

// ====================================================================== research
export function ResearchForm({ onRun, busy, disabled }: { onRun: (b: Record<string, unknown>) => void; busy: boolean; disabled?: boolean }) {
  const [brief, setBrief] = useState("Analyse our audience and the competitors in our profile. What should we do differently?");
  const [save, setSave] = useState(true);
  return (
    <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); onRun({ kind: "research", brief, save }); }}>
      <Notice tone="warning" title="Based on what you've added">
        Live web research isn't connected, so the analysis uses the audience and competitor notes in the profile and any documents you upload.
      </Notice>
      <Field label="Question" htmlFor="rb"><Textarea id="rb" value={brief} onChange={(e) => setBrief(e.target.value)} /></Field>
      <label className="inline-flex items-center gap-2 text-[14px]"><input type="checkbox" className="h-4 w-4 accent-[rgb(var(--orange))]" checked={save} onChange={(e) => setSave(e.target.checked)} />Save the result to the library</label>
      <div><Button type="submit" ai loading={busy} disabled={disabled || brief.trim().length < 3}>Analyse</Button></div>
    </form>
  );
}

export function TextResult({ ex }: { ex: Exchange }) {
  const { base } = useWs();
  return (
    <div className="flex flex-col gap-4">
      <RunPanel run={ex.run} />
      <Card><Markdown text={ex.assistant_message.content} /></Card>
      {ex.run.saved_asset_id && <Link href={`${base}/library?open=${ex.run.saved_asset_id}`} className="font-semibold text-orange-text underline">Saved to the library: open it</Link>}
    </div>
  );
}
