"use client";
import { Download, Plus, Trash2, Upload, Users } from "lucide-react";
import { useMemo, useState } from "react";
import { api, del, downloadUrl, errorText, post, put, useApi } from "@/lib/api";
import type { Exchange, Metric, Platform, Report } from "@/lib/types";
import { PLATFORMS, platformLabel } from "@/lib/types";
import { RunPanel } from "@/components/RunPanel";
import { useWs } from "@/components/Shell";
import { SyncButton, useConnections } from "@/components/Integrations";
import { Button, Card, EmptyState, Field, Input, LinkButton, Markdown, Modal, Notice, PageHeader, SectionTitle, Select, Skeleton,
  Stat, Tabs, fmtDate, num, useToast } from "@/components/ui";

const ymd = (d: Date) => d.toISOString().slice(0, 10);
function preset(p: string): [string, string] {
  const now = new Date();
  if (p === "last") return [ymd(new Date(Date.UTC(now.getFullYear(), now.getMonth() - 1, 1))), ymd(new Date(Date.UTC(now.getFullYear(), now.getMonth(), 0)))];
  if (p === "30") { const s = new Date(now); s.setDate(s.getDate() - 29); return [ymd(s), ymd(now)]; }
  return [ymd(new Date(Date.UTC(now.getFullYear(), now.getMonth(), 1))), ymd(now)];
}
const TEMPLATE = "title,platform,published_on,post_url,impressions,reach,likes,comments,shares,saves,clicks,video_views\n" +
  "Example post,instagram,2026-11-03,https://instagram.com/p/example,1200,900,80,6,4,10,3,\n";

function Bars({ rows }: { rows: Report["by_platform"] }) {
  const max = Math.max(1, ...rows.map((r) => Math.max(r.impressions ?? 0, r.engagements)));
  return (
    <div className="flex flex-col gap-3" role="img" aria-label="Impressions and engagements by platform">
      {rows.map((r) => (
        <div key={r.platform} className="grid grid-cols-[96px_1fr_auto] items-center gap-3 text-[14px]">
          <span className="font-semibold">{platformLabel(r.platform)}</span>
          <div className="relative h-6 overflow-hidden rounded-s bg-sunken">
            <div className="h-full rounded-s bg-d1 transition-all" style={{ width: `${((r.impressions ?? 0) / max) * 100}%` }} />
            <div className="absolute inset-y-1 left-0 rounded-s bg-orange" style={{ width: `${(r.engagements / max) * 100}%` }} />
          </div>
          <span className="font-mono text-[12px] tabular text-muted">{num(r.impressions)} / {num(r.engagements)}</span>
        </div>))}
      <div className="flex gap-4 text-[12px] text-muted"><span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-d1" />Impressions</span>
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-orange" />Engagements</span></div>
    </div>
  );
}

export default function Reports() {
  const { ws, canWrite, base } = useWs();
  const toast = useToast();
  const conns = useConnections();
  const yt = conns.data?.connections.find((c) => c.provider === "youtube");
  const [p, setP] = useState("this");
  const [[start, end], setRange] = useState(preset("this"));
  const q = `start=${start}&end=${end}`;
  const rep = useApi<Report>(`/v1/workspaces/${ws.id}/creator/report?${q}`);
  const rows = useApi<Metric[]>(`/v1/workspaces/${ws.id}/creator/metrics?${q}`);
  const [modal, setModal] = useState<"" | "add" | "csv" | "followers">("");
  const [narr, setNarr] = useState<Exchange | null>(null);
  const [writing, setWriting] = useState(false);
  const reload = () => { rep.reload(); rows.reload(); setNarr(null); };
  const exportQ = `${q}${narr ? `&narrative_run_id=${narr.run.id}` : ""}`;
  const t = rep.data?.totals;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Performance reports" description={yt ? "Built from the figures your team records plus YouTube Analytics (read-only). Other platforms aren't connected, so their numbers come from you." : "Built from the figures your team records. No platform analytics are connected, so nothing is fetched automatically."}>
        <Button variant="secondary" icon={<Users className="h-4 w-4" />} disabled={!canWrite} onClick={() => setModal("followers")}>Followers</Button>
        <Button variant="secondary" icon={<Upload className="h-4 w-4" />} disabled={!canWrite} onClick={() => setModal("csv")}>Upload CSV</Button>
        <Button icon={<Plus className="h-4 w-4" />} disabled={!canWrite} onClick={() => setModal("add")}>Add figures</Button>
      </PageHeader>
      {conns.data && (yt
        ? <div className="flex flex-wrap items-center gap-3 rounded-m border border-line bg-raised p-3 text-[14px]">
            <span className="font-semibold">YouTube: {yt.account_label}</span>
            <span className="text-muted">{yt.status === "needs_reauth" ? "Needs reconnecting in Settings" : `Last sync ${yt.last_sync_at ? fmtDate(yt.last_sync_at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "never"}`}</span>
            {yt.last_error && <span className="text-danger">{yt.last_error}</span>}
            <span className="ml-auto"><SyncButton conn={yt} onDone={() => { conns.reload(); reload(); }} /></span>
          </div>
        : conns.data.available.some((a) => a.key === "youtube" && a.configured) &&
          <p className="text-[14px] text-muted">Have a YouTube channel? <a className="font-semibold text-orange-text underline" href={`${base}/settings#integrations`}>Connect YouTube Analytics</a> (read-only) to pull views, likes, comments and shares.</p>)}
      <div className="flex flex-wrap items-end gap-3">
        <Tabs value={p} onChange={(v) => { setP(v); if (v !== "custom") setRange(preset(v)); setNarr(null); }}
          items={[{ id: "this", label: "This month" }, { id: "last", label: "Last month" }, { id: "30", label: "Last 30 days" }, { id: "custom", label: "Custom" }]} />
        {p === "custom" && <>
          <Field label="From" htmlFor="rs"><Input id="rs" type="date" value={start} onChange={(e) => setRange([e.target.value, end])} /></Field>
          <Field label="To" htmlFor="re"><Input id="re" type="date" value={end} onChange={(e) => setRange([start, e.target.value])} /></Field></>}
      </div>
      {!rep.data ? <Skeleton className="h-40" /> : (
        <>
          {rep.data.caveats.length > 0 && <Notice tone="warning" title="About this data"><ul className="list-disc pl-5">{rep.data.caveats.map((c, i) => <li key={i}>{c}</li>)}</ul></Notice>}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Stat label="Posts with figures" value={rep.data.posts} hint={`${rep.data.posts_marked_published} marked posted`} />
            <Stat label="Impressions" value={num(t!.impressions)} />
            <Stat label="Reach" value={num(t!.reach)} />
            <Stat label="Engagements" value={num(t!.engagements)} hint="Likes, comments, shares, saves" />
            <Stat label="Engagement rate" value={t!.engagement_rate === null ? "–" : `${t!.engagement_rate}%`} hint="Engagements ÷ impressions" />
          </div>
          {rep.data.posts === 0 ? (
            <EmptyState title="No figures recorded for this period" action={canWrite && <Button onClick={() => setModal("add")}>Add figures</Button>}>
              Copy the numbers from each platform's insights page, or upload them as a CSV.</EmptyState>
          ) : (
            <div className="grid gap-6 lg:grid-cols-2">
              <Card><SectionTitle>By platform</SectionTitle><Bars rows={rep.data.by_platform} /></Card>
              <Card><SectionTitle>Top posts</SectionTitle>
                <ol className="flex flex-col gap-2">{rep.data.top_posts.map((tp, i) => (
                  <li key={i} className="flex items-center gap-3 text-[14px]"><span className="grid h-6 w-6 place-items-center rounded-full bg-sunken font-mono text-[12px]">{i + 1}</span>
                    <span className="min-w-0 flex-1 truncate">{tp.url ? <a href={tp.url} target="_blank" rel="noopener noreferrer nofollow" className="underline">{tp.label}</a> : tp.label}</span>
                    <span className="text-muted">{platformLabel(tp.platform)}</span><span className="font-mono text-[12px] tabular">{num(tp.engagements)}</span></li>))}</ol>
                {rep.data.followers.length > 0 && <div className="mt-4 border-t border-line pt-3"><div className="mb-1 text-[14px] font-semibold">Followers</div>
                  {rep.data.followers.map((f) => <div key={f.platform} className="flex justify-between text-[14px]"><span>{platformLabel(f.platform)}</span>
                    <span className="font-mono tabular">{num(f.first)} → {num(f.last)} <span className={f.change >= 0 ? "text-success" : "text-danger"}>({f.change >= 0 ? "+" : ""}{num(f.change)})</span></span></div>)}</div>}
              </Card>
            </div>
          )}
          <Card className="flex flex-col gap-3">
            <SectionTitle right={<Button ai size="sm" loading={writing} disabled={!canWrite || rep.data.posts === 0} onClick={async () => {
              setWriting(true);
              try { setNarr(await post<Exchange>(`/v1/workspaces/${ws.id}/creator/generate`, { kind: "report", brief: "Summarise performance for the client and suggest next steps.", start_date: start, end_date: end })); }
              catch (e) { toast(errorText(e), "danger"); } finally { setWriting(false); }
            }}>Write summary</Button>}>Summary for the client</SectionTitle>
            {narr ? <><RunPanel run={narr.run} /><Markdown text={narr.assistant_message.content} /></>
              : <p className="text-[14px] text-muted">The AI can explain these figures in plain words. It only uses the numbers above.</p>}
          </Card>
          <div className="flex flex-wrap gap-2">
            <LinkButton download href={downloadUrl(`/v1/workspaces/${ws.id}/creator/report/export?format=html&${exportQ}`)}><Download className="h-4 w-4" />Report (HTML)</LinkButton>
            <LinkButton download href={downloadUrl(`/v1/workspaces/${ws.id}/creator/report/export?format=md&${exportQ}`)}><Download className="h-4 w-4" />Report (Markdown)</LinkButton>
            <LinkButton download href={downloadUrl(`/v1/workspaces/${ws.id}/creator/report/export?format=csv&${q}`)}><Download className="h-4 w-4" />Figures (CSV)</LinkButton>
          </div>
        </>
      )}
      <Card>
        <SectionTitle>Recorded figures</SectionTitle>
        {(rows.data ?? []).length === 0 ? <p className="text-muted">None for this period.</p> : (
          <div className="overflow-x-auto"><table className="w-full text-[13px]">
            <thead className="bg-sunken text-left"><tr>{["Date", "Post", "Platform", "Impr.", "Reach", "Likes", "Comm.", "Shares", "Saves", "Clicks", "Source", ""].map((h) => <th key={h} className="px-2 py-1.5">{h}</th>)}</tr></thead>
            <tbody>{rows.data!.map((m) => (
              <tr key={m.id} className="border-t border-line">
                <td className="whitespace-nowrap px-2 py-1.5 font-mono">{m.published_on}</td><td className="max-w-[220px] truncate px-2">{m.post_label}</td>
                <td className="px-2">{platformLabel(m.platform)}</td>
                {(["impressions", "reach", "likes", "comments", "shares", "saves", "clicks"] as const).map((k) => <td key={k} className="px-2 font-mono tabular">{num(m[k])}</td>)}
                <td className="px-2 text-muted">{m.source === "csv_import" ? "CSV" : m.source === "integration" ? "YouTube" : "Manual"}</td>
                <td className="px-2">{canWrite && <button aria-label={`Delete ${m.post_label}`} className="grid h-8 w-8 place-items-center rounded-s hover:bg-sunken"
                  onClick={async () => { await del(`/v1/workspaces/${ws.id}/creator/metrics/${m.id}`); toast("Deleted"); reload(); }}><Trash2 className="h-4 w-4" /></button>}</td>
              </tr>))}</tbody></table></div>
        )}
      </Card>
      {modal === "add" && <AddModal onClose={() => setModal("")} onSaved={reload} />}
      {modal === "csv" && <CsvModal onClose={() => setModal("")} onSaved={reload} />}
      {modal === "followers" && <FollowersModal onClose={() => setModal("")} onSaved={reload} />}
    </div>
  );
}

function AddModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { ws } = useWs();
  const toast = useToast();
  const [f, setF] = useState<Record<string, string>>({ platform: "instagram", post_label: "", published_on: ymd(new Date()), post_url: "" });
  const fields = ["impressions", "reach", "likes", "comments", "shares", "saves", "clicks", "video_views"];
  const [busy, setBusy] = useState(false);
  return (
    <Modal open onClose={onClose} title="Add figures for a post" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button>
      <Button loading={busy} disabled={!f.post_label.trim()} onClick={async () => {
        setBusy(true);
        const body: Record<string, unknown> = { platform: f.platform, post_label: f.post_label, published_on: f.published_on, post_url: f.post_url || null };
        for (const k of fields) if (f[k]) body[k] = Number(f[k]);
        try { await post(`/v1/workspaces/${ws.id}/creator/metrics`, body); toast("Figures saved"); onSaved(); onClose(); }
        catch (e) { toast(errorText(e), "danger"); } finally { setBusy(false); }
      }}>Save</Button></>}>
      <div className="flex flex-col gap-4">
        <Notice>Copy these from the platform's insights. Leave a box empty if you don't have that number.</Notice>
        <Field label="Post" htmlFor="ml"><Input id="ml" value={f.post_label} onChange={(e) => setF({ ...f, post_label: e.target.value })} placeholder="A name you'll recognise" /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Platform" htmlFor="mp"><Select id="mp" value={f.platform} onChange={(e) => setF({ ...f, platform: e.target.value })}>{PLATFORMS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</Select></Field>
          <Field label="Posted on" htmlFor="md"><Input id="md" type="date" value={f.published_on} onChange={(e) => setF({ ...f, published_on: e.target.value })} /></Field>
        </div>
        <Field label="Link (optional)" htmlFor="mu"><Input id="mu" value={f.post_url} onChange={(e) => setF({ ...f, post_url: e.target.value })} placeholder="https://" /></Field>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{fields.map((k) => (
          <Field key={k} label={k.replace("_", " ")} htmlFor={`m-${k}`}><Input id={`m-${k}`} inputMode="numeric" pattern="[0-9]*" value={f[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value.replace(/\D/g, "") })} /></Field>))}</div>
      </div>
    </Modal>
  );
}

function CsvModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { ws } = useWs();
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [platform, setPlatform] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const template = useMemo(() => URL.createObjectURL(new Blob([TEMPLATE], { type: "text/csv" })), []);
  return (
    <Modal open onClose={onClose} title="Upload figures (CSV)" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button>
      <Button loading={busy} disabled={!file} onClick={async () => {
        setBusy(true); setErr("");
        const fd = new FormData(); fd.append("file", file!); if (platform) fd.append("platform", platform);
        try { const r = await api.upload<{ imported: number }>(`/v1/workspaces/${ws.id}/creator/metrics/import`, fd); toast(`Imported ${r.imported} row(s)`); onSaved(); onClose(); }
        catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
      }}>Import</Button></>}>
      <div className="flex flex-col gap-4">
        <p className="text-[14px]">Columns: <span className="font-mono text-[13px]">title, platform, published_on</span> (required) plus any of impressions, reach, likes, comments, shares, saves, clicks, video_views, post_url. If any row has a problem, nothing is imported and every problem is listed.</p>
        <a href={template} download="figures-template.csv" className="text-[14px] font-semibold text-orange-text underline">Download a template</a>
        {err && <Notice tone="danger">{err}</Notice>}
        <Field label="CSV file" htmlFor="cf"><Input id="cf" type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
        <Field label="Platform for every row (if the file has no platform column)" htmlFor="cp">
          <Select id="cp" value={platform} onChange={(e) => setPlatform(e.target.value)}><option value="">From the file</option>{PLATFORMS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</Select></Field>
      </div>
    </Modal>
  );
}

function FollowersModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { ws } = useWs();
  const toast = useToast();
  const [f, setF] = useState({ platform: "instagram" as Platform, captured_on: ymd(new Date()), followers: "" });
  return (
    <Modal open onClose={onClose} title="Record follower count" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button>
      <Button disabled={!f.followers} onClick={async () => {
        try { await put(`/v1/workspaces/${ws.id}/creator/followers`, { ...f, followers: Number(f.followers) }); toast("Saved"); onSaved(); onClose(); }
        catch (e) { toast(errorText(e), "danger"); }
      }}>Save</Button></>}>
      <div className="flex flex-col gap-4">
        <p className="text-[14px] text-muted">Record it at the start and end of each month to see growth. Saving the same day again replaces it.</p>
        <Field label="Platform" htmlFor="fp"><Select id="fp" value={f.platform} onChange={(e) => setF({ ...f, platform: e.target.value as Platform })}>{PLATFORMS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</Select></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Date" htmlFor="fd"><Input id="fd" type="date" value={f.captured_on} onChange={(e) => setF({ ...f, captured_on: e.target.value })} /></Field>
          <Field label="Followers" htmlFor="fn"><Input id="fn" inputMode="numeric" value={f.followers} onChange={(e) => setF({ ...f, followers: e.target.value.replace(/\D/g, "") })} /></Field>
        </div>
      </div>
    </Modal>
  );
}
