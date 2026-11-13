"use client";
import { ChevronLeft, ChevronRight, Download, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { del, downloadUrl, errorText, patch, post, useApi } from "@/lib/api";
import type { Asset, CalendarItem, ClientProfile, Page, Platform } from "@/lib/types";
import { PLATFORMS, platformLabel } from "@/lib/types";
import { useWs } from "@/components/Shell";
import { CalendarForm, CalendarResult, Generating, useGenerate } from "@/components/studio";
import { Button, ConfirmButton, Drawer, Field, Input, LinkButton, Modal, Notice, PageHeader, Select, StatusBadge, Textarea,
  cx, fmtDate, fmtTime, useToast } from "@/components/ui";

const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const CHIP: Record<string, string> = { planned: "bg-sunken", drafted: "bg-orange-soft", ready: "bg-success-soft",
  published_manually: "bg-d1-soft", skipped: "bg-sunken opacity-60 line-through" };

export default function CalendarPage() {
  const { ws, canWrite } = useWs();
  const [month, setMonth] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const gridStart = useMemo(() => { const d = new Date(month); d.setDate(1 - ((d.getDay() + 6) % 7)); return d; }, [month]);
  const days = useMemo(() => Array.from({ length: 42 }, (_, i) => { const d = new Date(gridStart); d.setDate(d.getDate() + i); return d; }), [gridStart]);
  const range = `start=${ymd(days[0])}&end=${ymd(days[41])}`;
  const cal = useApi<CalendarItem[]>(`/v1/workspaces/${ws.id}/creator/calendar?${range}`);
  const profile = useApi<ClientProfile>(`/v1/workspaces/${ws.id}/client-account`);
  const [edit, setEdit] = useState<CalendarItem | null>(null);
  const [add, setAdd] = useState<string | null>(null);
  const [plan, setPlan] = useState(false);
  const byDay = useMemo(() => {
    const m: Record<string, CalendarItem[]> = {};
    for (const i of cal.data ?? []) (m[ymd(new Date(i.scheduled_for))] ??= []).push(i);
    return m;
  }, [cal.data]);
  const today = ymd(new Date());
  const monthItems = (cal.data ?? []).filter((i) => new Date(i.scheduled_for).getMonth() === month.getMonth());

  return (
    <div>
      <PageHeader title="Content calendar" description="Plan when each post goes out. You post it; then mark it as posted here.">
        <LinkButton download href={downloadUrl(`/v1/workspaces/${ws.id}/creator/calendar/export?format=csv&${range}`)}><Download className="h-4 w-4" />CSV</LinkButton>
        <LinkButton download href={downloadUrl(`/v1/workspaces/${ws.id}/creator/calendar/export?format=ics&${range}`)}><Download className="h-4 w-4" />Calendar file</LinkButton>
        <Button variant="secondary" icon={<Plus className="h-4 w-4" />} disabled={!canWrite} onClick={() => setAdd(today)}>Add post</Button>
        <Button ai disabled={!canWrite} onClick={() => setPlan(true)}>Plan with AI</Button>
      </PageHeader>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" aria-label="Previous month" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}><ChevronLeft className="h-4 w-4" /></Button>
        <h2 className="min-w-0 text-center sm:min-w-[160px] text-[20px] font-semibold">{month.toLocaleDateString("en-GB", { month: "long", year: "numeric" })}</h2>
        <Button variant="ghost" size="sm" aria-label="Next month" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}><ChevronRight className="h-4 w-4" /></Button>
        <Button variant="ghost" size="sm" onClick={() => { const d = new Date(); setMonth(new Date(d.getFullYear(), d.getMonth(), 1)); }}>Today</Button>
        <span className="ml-auto font-mono text-[13px] text-muted">{monthItems.length} this month</span>
      </div>

      <div className="hidden overflow-hidden rounded-m border border-line md:block">
        <div className="grid grid-cols-7 bg-sunken text-[12px] font-semibold uppercase tracking-[0.6px] text-muted">
          {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <div key={d} className="px-2 py-2">{d}</div>)}
        </div>
        <div className="grid grid-cols-7">
          {days.map((d) => {
            const key = ymd(d);
            const inMonth = d.getMonth() === month.getMonth();
            return (
              <div key={key} className={cx("group relative min-h-[112px] border-t border-l border-line p-1.5 first:border-l-0 [&:nth-child(7n+1)]:border-l-0",
                inMonth ? "bg-raised" : "bg-cream/60")}>
                <div className="flex items-center justify-between">
                  <span className={cx("grid h-6 w-6 place-items-center rounded-full font-mono text-[12px]", key === today ? "bg-orange text-on-orange" : inMonth ? "" : "text-muted")}>{d.getDate()}</span>
                  {canWrite && <button aria-label={`Add post on ${fmtDate(d)}`} onClick={() => setAdd(key)}
                    className="grid h-6 w-6 place-items-center rounded-s text-muted opacity-0 transition hover:bg-sunken group-hover:opacity-100 focus:opacity-100"><Plus className="h-3.5 w-3.5" /></button>}
                </div>
                <ul className="mt-1 flex flex-col gap-1">
                  {(byDay[key] ?? []).map((i) => (
                    <li key={i.id}><button onClick={() => setEdit(i)}
                      className={cx("w-full truncate rounded-s px-1.5 py-1 text-left text-[12px] transition hover:ring-1 hover:ring-control", CHIP[i.status])}
                      title={`${i.title} · ${platformLabel(i.platform)} · ${i.status}`}>
                      <span className="font-mono">{fmtTime(i.scheduled_for)}</span> <span className="font-semibold">{platformLabel(i.platform)}</span> {i.title}
                    </button></li>))}
                </ul>
              </div>
            );
          })}
        </div>
      </div>

      <ul className="flex flex-col gap-2 md:hidden">
        {monthItems.length === 0 && <li className="rounded-m border border-dashed border-control/60 p-6 text-center text-muted">Nothing planned this month.</li>}
        {monthItems.map((i) => (
          <li key={i.id}><button onClick={() => setEdit(i)} className="flex w-full items-center gap-3 rounded-m border border-line bg-raised p-3 text-left">
            <div className="w-14 font-mono text-[12px] text-muted">{fmtDate(i.scheduled_for, { weekday: "short", day: "numeric" })}<br />{fmtTime(i.scheduled_for)}</div>
            <div className="min-w-0 flex-1"><div className="truncate font-semibold">{i.title}</div><div className="text-[13px] text-muted">{platformLabel(i.platform)}</div></div>
            <StatusBadge status={i.status} /></button></li>))}
      </ul>

      <div className="mt-4 flex flex-wrap gap-2 text-[12px]">{Object.keys(CHIP).map((s) => <StatusBadge key={s} status={s} />)}</div>

      {add && <ItemModal date={add} platforms={profile.data?.platforms ?? []} onClose={() => setAdd(null)} onSaved={cal.reload} />}
      {edit && <ItemDrawer item={edit} onClose={() => setEdit(null)} onChanged={() => { cal.reload(); setEdit(null); }} />}
      {plan && <PlanModal platforms={profile.data?.platforms ?? []} onClose={() => { setPlan(false); cal.reload(); }} />}
    </div>
  );
}

function ItemModal({ date, platforms, onClose, onSaved }: { date: string; platforms: string[]; onClose: () => void; onSaved: () => void }) {
  const { ws } = useWs();
  const toast = useToast();
  const [f, setF] = useState({ title: "", platform: (platforms[0] ?? "instagram") as Platform, format: "post", date, time: "09:00", pillar: "", notes: "" });
  const [busy, setBusy] = useState(false);
  return (
    <Modal open onClose={onClose} title="Plan a post" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button>
      <Button loading={busy} disabled={!f.title.trim()} onClick={async () => {
        setBusy(true);
        try {
          await post(`/v1/workspaces/${ws.id}/creator/calendar`, { title: f.title, platform: f.platform, format: f.format,
            pillar: f.pillar || null, notes: f.notes, scheduled_for: new Date(`${f.date}T${f.time}`).toISOString() });
          toast("Added to the calendar"); onSaved(); onClose();
        } catch (e) { toast(errorText(e), "danger"); } finally { setBusy(false); }
      }}>Add</Button></>}>
      <div className="flex flex-col gap-4">
        <Field label="Working title" htmlFor="it"><Input id="it" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Date" htmlFor="id"><Input id="id" type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
          <Field label="Time" htmlFor="itm"><Input id="itm" type="time" value={f.time} onChange={(e) => setF({ ...f, time: e.target.value })} /></Field>
          <Field label="Platform" htmlFor="ip"><Select id="ip" value={f.platform} onChange={(e) => setF({ ...f, platform: e.target.value as Platform })}>
            {PLATFORMS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</Select></Field>
          <Field label="Format" htmlFor="if"><Select id="if" value={f.format} onChange={(e) => setF({ ...f, format: e.target.value })}>
            {["post", "carousel", "reel", "story", "thread", "video", "short", "live", "article", "pin"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
        </div>
        <Field label="Content pillar (optional)" htmlFor="ipl"><Input id="ipl" value={f.pillar} onChange={(e) => setF({ ...f, pillar: e.target.value })} /></Field>
        <Field label="Notes" htmlFor="in"><Textarea id="in" rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
      </div>
    </Modal>
  );
}

function ItemDrawer({ item, onClose, onChanged }: { item: CalendarItem; onClose: () => void; onChanged: () => void }) {
  const { ws, base, canWrite } = useWs();
  const toast = useToast();
  const assets = useApi<Page<Asset>>(`/v1/workspaces/${ws.id}/assets?limit=100`);
  const d = new Date(item.scheduled_for);
  const [f, setF] = useState({ title: item.title, notes: item.notes, status: item.status, asset_id: item.asset_id ?? "",
    date: ymd(d), time: `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}` });
  const [pub, setPub] = useState(false);
  const [url, setUrl] = useState(item.published_url ?? "");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const path = `/v1/workspaces/${ws.id}/creator/calendar/${item.id}`;
  const done = item.status === "published_manually";
  async function save() {
    setBusy(true);
    try {
      await patch(path, { title: f.title, notes: f.notes, asset_id: f.asset_id || null,
        scheduled_for: new Date(`${f.date}T${f.time}`).toISOString(), ...(done ? {} : { status: f.status }) });
      toast("Saved"); onChanged();
    } catch (e) { toast(errorText(e), "danger"); } finally { setBusy(false); }
  }
  return (
    <Drawer open onClose={onClose} title={item.title} footer={canWrite && <>
      <Button onClick={save} loading={busy}>Save</Button>
      {!done && <Button variant="secondary" onClick={() => setPub(true)}>Mark as posted</Button>}
      {done && <Button variant="secondary" onClick={async () => { await patch(path, { status: "ready" }); toast("No longer marked as posted"); onChanged(); }}>Undo posted</Button>}
      <span className="flex-1" />
      <ConfirmButton label="Remove from calendar?" onConfirm={async () => { await del(path); toast("Removed"); onChanged(); }}>Remove</ConfirmButton>
    </>}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2"><StatusBadge status={item.status} /><span className="text-[13px] text-muted">{platformLabel(item.platform)} · {item.format}{item.pillar ? ` · ${item.pillar}` : ""}{item.source === "ai_plan" ? " · from AI plan" : ""}</span></div>
        {done && <Notice tone="success" title="Marked as posted by your team">
          {fmtDate(item.published_at!, { day: "numeric", month: "short", year: "numeric" })} {item.published_url && <a href={item.published_url} target="_blank" rel="noopener noreferrer nofollow" className="underline">View post</a>}
          <div className="text-[13px] text-muted">This is a record you entered; it isn't checked against the platform.</div></Notice>}
        <Field label="Title" htmlFor="et"><Input id="et" value={f.title} disabled={!canWrite} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Date" htmlFor="ed"><Input id="ed" type="date" value={f.date} disabled={!canWrite} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
          <Field label="Time" htmlFor="etm"><Input id="etm" type="time" value={f.time} disabled={!canWrite} onChange={(e) => setF({ ...f, time: e.target.value })} /></Field>
        </div>
        {!done && <Field label="Status" htmlFor="es"><Select id="es" value={f.status} disabled={!canWrite} onChange={(e) => setF({ ...f, status: e.target.value as CalendarItem["status"] })}>
          <option value="planned">Planned</option><option value="drafted">Drafted</option><option value="ready">Ready</option><option value="skipped">Skipped</option></Select></Field>}
        <Field label="Content" htmlFor="ea" hint={item.asset_status ? `Linked content is ${item.asset_status.replace("_", " ")}.` : "Link a saved draft from the library."}>
          <Select id="ea" value={f.asset_id} disabled={!canWrite} onChange={(e) => setF({ ...f, asset_id: e.target.value })}>
            <option value="">Not linked</option>
            {assets.data?.data.filter((a) => a.status !== "archived").map((a) => <option key={a.id} value={a.id}>{a.title.slice(0, 70)} ({a.status.replace("_", " ")})</option>)}
          </Select></Field>
        {item.asset_id && <a href={`${base}/library?open=${item.asset_id}`} className="text-[14px] font-semibold text-orange-text underline">Open linked content</a>}
        <Field label="Notes" htmlFor="en"><Textarea id="en" rows={4} value={f.notes} disabled={!canWrite} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
      </div>
      {pub && (
        <Modal open onClose={() => setPub(false)} title="Mark as posted" footer={<><Button variant="ghost" onClick={() => setPub(false)}>Cancel</Button>
          <Button disabled={!confirm || (!!url && !/^https?:\/\/\S+$/.test(url))} onClick={async () => {
            try { await post(`${path}/mark-published`, { published_url: url || undefined }); toast("Marked as posted"); setPub(false); onChanged(); }
            catch (e) { toast(errorText(e), "danger"); }
          }}>Mark as posted</Button></>}>
          <div className="flex flex-col gap-4">
            <Notice>Nothing is posted from here. Use this after you've posted it on {platformLabel(item.platform)} yourself.</Notice>
            {item.asset_id && item.asset_status !== "approved" && item.asset_status !== "posted" &&
              <Notice tone="warning">The linked content isn't approved yet, so this will be refused. Approve it first.</Notice>}
            <Field label="Link to the live post (optional)" htmlFor="pu" error={url && !/^https?:\/\/\S+$/.test(url) ? "Use a full link starting with https://" : undefined}>
              <Input id="pu" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" /></Field>
            <label className="inline-flex items-center gap-2 text-[14px]"><input type="checkbox" className="h-4 w-4 accent-[rgb(var(--orange))]" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />I've posted this myself</label>
          </div>
        </Modal>
      )}
    </Drawer>
  );
}

function PlanModal({ platforms, onClose }: { platforms: string[]; onClose: () => void }) {
  const g = useGenerate();
  return (
    <Modal open wide onClose={onClose} title="Plan the calendar with AI">
      {!g.result && !g.busy && <CalendarForm onRun={g.run} busy={g.busy} platforms={platforms} />}
      {g.error && <div className="mt-3"><Notice tone="danger">{g.error}</Notice></div>}
      {g.busy && <Generating label="Planning the calendar…" />}
      {g.result && (g.result.run.status === "succeeded" ? <CalendarResult ex={g.result} onImported={onClose} />
        : <Notice tone="warning">{g.result.assistant_message.content}</Notice>)}
    </Modal>
  );
}
