"use client";
import { CalendarPlus, History, MessageSquare } from "lucide-react";
import { useEffect, useState } from "react";
import { del, errorText, patch, post, useApi } from "@/lib/api";
import type { Asset, AssetVersion, Comment, Platform } from "@/lib/types";
import { PLATFORMS } from "@/lib/types";
import { useWs } from "./Shell";
import { Button, ConfirmButton, CopyButton, Drawer, Field, Input, Modal, Notice, Select, StatusBadge, Textarea, fmtDate, fmtTime, useToast } from "./ui";

export function AssetDrawer({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const { ws, canWrite, isAdmin } = useWs();
  const toast = useToast();
  const base = `/v1/workspaces/${ws.id}`;
  const asset = useApi<Asset>(`${base}/assets/${id}`);
  const versions = useApi<AssetVersion[]>(`${base}/assets/${id}/versions`);
  const comments = useApi<Comment[]>(`${base}/creator/assets/${id}/comments`);
  const latest = versions.data?.[0];
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [sched, setSched] = useState(false);
  const [view, setView] = useState<AssetVersion | null>(null);
  useEffect(() => { if (asset.data) setTitle(asset.data.title); }, [asset.data]);
  useEffect(() => { if (latest) setText(latest.body_text); }, [latest]);

  const refresh = () => { asset.reload(); versions.reload(); comments.reload(); onChanged(); };
  async function act(label: string, fn: () => Promise<unknown>, ok: string) {
    setBusy(label);
    try { await fn(); toast(ok); setNote(""); refresh(); } catch (e) { toast(errorText(e), "danger"); } finally { setBusy(""); }
  }
  const a = asset.data;
  const dirty = !!latest && (text !== latest.body_text || (a && title !== a.title));
  const editable = canWrite && a && a.status !== "posted" && a.status !== "archived";

  return (
    <Drawer open onClose={onClose} title={a?.title ?? "Content"}
      footer={a && (
        <div className="flex w-full flex-wrap items-center gap-2">
          {editable && <Button disabled={!dirty} loading={busy === "save"} onClick={() => act("save", async () => {
            if (title !== a.title) await patch(`${base}/assets/${id}`, { title });
            if (text !== latest!.body_text) await post(`${base}/assets/${id}/versions`, { body: { ...latest!.body, edited_text: text }, body_text: text });
          }, "Saved a new version")}>Save changes</Button>}
          {canWrite && a.status === "draft" && <Button variant="secondary" loading={busy === "submit"} disabled={dirty}
            onClick={() => act("submit", () => post(`${base}/creator/assets/${id}/submit`, { note }), "Sent for approval")}>Send for approval</Button>}
          {canWrite && a.status === "in_review" && (
            <>
              {isAdmin && <Button loading={busy === "approve"} disabled={dirty}
                onClick={() => act("approve", () => post(`${base}/creator/assets/${id}/decision`, { decision: "approve", comment: note }), "Approved")}>Approve</Button>}
              <Button variant="secondary" loading={busy === "changes"} disabled={!note.trim()}
                onClick={() => act("changes", () => post(`${base}/creator/assets/${id}/decision`, { decision: "request_changes", comment: note }), "Changes requested")}>Request changes</Button>
            </>
          )}
          <CopyButton text={text} label="Copy text" />
          {canWrite && <Button variant="ghost" size="sm" icon={<CalendarPlus className="h-4 w-4" />} onClick={() => setSched(true)}>Schedule</Button>}
          <span className="flex-1" />
          {canWrite && a.status !== "archived" && <Button variant="ghost" size="sm" onClick={() => act("archive", () => patch(`${base}/assets/${id}`, { status: "archived" }), "Archived")}>Archive</Button>}
          {canWrite && <ConfirmButton label="Delete this?" onConfirm={async () => { await del(`${base}/assets/${id}`); toast("Deleted"); onChanged(); onClose(); }}>Delete</ConfirmButton>}
        </div>
      )}>
      {!a ? <p className="text-muted">Loading…</p> : (
        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap items-center gap-2"><StatusBadge status={a.status} /><span className="text-[13px] text-muted">{a.type} · version {a.current_version} · updated {fmtDate(a.updated_at)} {fmtTime(a.updated_at)}</span></div>
          {a.status === "approved" && <Notice tone="success">Approved. Post it yourself, then mark the calendar item as posted. Editing it sends it back for approval.</Notice>}
          {a.status === "posted" && <Notice>Marked as posted by your team. It's locked to keep a record of what went out.</Notice>}
          <Field label="Title" htmlFor="at"><Input id="at" value={title} disabled={!editable} onChange={(e) => setTitle(e.target.value)} /></Field>
          <Field label="Content" htmlFor="ab"><Textarea id="ab" rows={12} value={text} disabled={!editable} onChange={(e) => setText(e.target.value)} />
            <div className="text-right font-mono text-[12px] text-muted">{text.length} characters</div></Field>
          {canWrite && (a.status === "draft" || a.status === "in_review") && (
            <Field label={a.status === "in_review" ? "Review comment" : "Note for the reviewer (optional)"} htmlFor="an">
              <Textarea id="an" rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder={a.status === "in_review" ? "Required when requesting changes" : ""} /></Field>
          )}

          <section>
            <h3 className="mb-2 flex items-center gap-2 text-[15px] font-semibold"><History className="h-4 w-4" />Versions</h3>
            <ul className="divide-y divide-line rounded-m border border-line bg-raised">
              {versions.data?.map((v) => (
                <li key={v.id} className="flex items-center justify-between gap-2 px-3 py-2 text-[14px]">
                  <span>v{v.version} · {v.source === "ai" ? "AI draft" : "Edited"} · {fmtDate(v.created_at)} {fmtTime(v.created_at)}</span>
                  <Button variant="ghost" size="sm" onClick={() => setView(v)}>View</Button>
                </li>))}
            </ul>
          </section>

          <section>
            <h3 className="mb-2 flex items-center gap-2 text-[15px] font-semibold"><MessageSquare className="h-4 w-4" />Review history</h3>
            {comments.data?.length === 0 && <p className="text-[14px] text-muted">No comments yet.</p>}
            <ol className="flex flex-col gap-2">
              {comments.data?.map((c) => (
                <li key={c.id} className="rounded-m bg-raised p-3 text-[14px]">
                  <div className="flex flex-wrap items-center gap-2 text-[13px]">
                    <span className="font-semibold">{c.via === "client_link" ? `${c.author_name} (client)` : "Team"}</span>
                    <StatusBadge status={{ submitted: "in_review", approved: "approved", changes_requested: "draft", comment: "planned" }[c.kind] ?? c.kind} />
                    <span className="text-muted">{c.kind.replace("_", " ")} · v{c.asset_version} · {fmtDate(c.created_at)}</span>
                  </div>
                  {c.body && <p className="mt-1 whitespace-pre-wrap">{c.body}</p>}
                </li>))}
            </ol>
            <CommentBox onSend={(body) => act("comment", () => post(`${base}/creator/assets/${id}/comments`, { body }), "Comment added")} />
          </section>
        </div>
      )}
      {view && (
        <Modal open onClose={() => setView(null)} title={`Version ${view.version}`}
          footer={editable && view.version !== latest?.version ? <Button onClick={() => { setText(view.body_text); setView(null); }}>Restore into editor</Button> : undefined}>
          <pre className="whitespace-pre-wrap font-sans text-[14px]">{view.body_text || "(empty)"}</pre>
        </Modal>
      )}
      {sched && a && <ScheduleModal asset={a} text={text} onClose={() => setSched(false)} onDone={refresh} />}
    </Drawer>
  );
}

function CommentBox({ onSend }: { onSend: (b: string) => void }) {
  const [b, setB] = useState("");
  return (
    <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (b.trim()) { onSend(b.trim()); setB(""); } }}>
      <Input aria-label="Add a comment" placeholder="Add a comment" value={b} onChange={(e) => setB(e.target.value)} />
      <Button type="submit" variant="secondary" disabled={!b.trim()}>Send</Button>
    </form>
  );
}

function ScheduleModal({ asset, onClose, onDone }: { asset: Asset; text: string; onClose: () => void; onDone: () => void }) {
  const { ws } = useWs();
  const toast = useToast();
  const guess = (asset.tags.find((t) => PLATFORMS.some((p) => p.id === t)) ?? "instagram") as Platform;
  const [f, setF] = useState({ date: new Date(Date.now() + 86400000).toISOString().slice(0, 10), time: "09:00", platform: guess });
  const [busy, setBusy] = useState(false);
  return (
    <Modal open onClose={onClose} title="Add to calendar" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button>
      <Button loading={busy} onClick={async () => {
        setBusy(true);
        try {
          await post(`/v1/workspaces/${ws.id}/creator/calendar`, { title: asset.title.slice(0, 200), platform: f.platform,
            scheduled_for: new Date(`${f.date}T${f.time}`).toISOString(), asset_id: asset.id, format: asset.type });
          toast("Added to the calendar"); onDone(); onClose();
        } catch (e) { toast(errorText(e), "danger"); } finally { setBusy(false); }
      }}>Add</Button></>}>
      <div className="flex flex-col gap-4">
        <p className="text-[14px] text-muted">This plans when you'll post it. Nothing is posted automatically.</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Date" htmlFor="sd"><Input id="sd" type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
          <Field label="Time" htmlFor="st"><Input id="st" type="time" value={f.time} onChange={(e) => setF({ ...f, time: e.target.value })} /></Field>
        </div>
        <Field label="Platform" htmlFor="sp"><Select id="sp" value={f.platform} onChange={(e) => setF({ ...f, platform: e.target.value as Platform })}>
          {PLATFORMS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</Select></Field>
      </div>
    </Modal>
  );
}
