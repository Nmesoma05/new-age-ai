"use client";
import { Download, History } from "lucide-react";
import { useEffect, useState } from "react";
import { del, downloadUrl, errorText, patch, post, useApi } from "@/lib/api";
import { tool, type Project } from "@/lib/biz";
import type { Asset, AssetVersion } from "@/lib/types";
import { useWs } from "../Shell";
import { Button, ConfirmButton, CopyButton, Drawer, Field, Input, LinkButton, Markdown, Modal, Select, Tabs, Textarea, fmtDate, fmtTime, useToast } from "../ui";

/** Edit a saved piece of business work: every save is a new version; nothing is sent anywhere. */
export function WorkDrawer({ id, projects, onClose, onChanged, api = "business", label }: { id: string; projects: Project[]; onClose: () => void;
  onChanged: () => void; api?: "business" | "freelancer"; label?: (a: Asset) => string }) {
  const { ws, canWrite } = useWs();
  const toast = useToast();
  const base = `/v1/workspaces/${ws.id}`;
  const asset = useApi<Asset & { project_id: string | null }>(`${base}/assets/${id}`);
  const versions = useApi<AssetVersion[]>(`${base}/assets/${id}/versions`);
  const latest = versions.data?.[0];
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"read" | "edit">("read");
  const [busy, setBusy] = useState("");
  const [view, setView] = useState<AssetVersion | null>(null);
  useEffect(() => { if (asset.data) setTitle(asset.data.title); }, [asset.data]);
  useEffect(() => { if (latest) setText(latest.body_text); }, [latest]);
  const a = asset.data;
  const dirty = !!latest && !!a && (text !== latest.body_text || title !== a.title);
  async function act(label: string, fn: () => Promise<unknown>, ok: string) {
    setBusy(label);
    try { await fn(); toast(ok); asset.reload(); versions.reload(); onChanged(); } catch (e) { toast(errorText(e), "danger"); } finally { setBusy(""); }
  }
  return (
    <Drawer open onClose={onClose} title={a?.title ?? "Saved work"}
      footer={a && <div className="flex w-full flex-wrap items-center gap-2">
        {canWrite && <Button disabled={!dirty} loading={busy === "save"} onClick={() => act("save", async () => {
          if (title !== a.title) await patch(`${base}/assets/${id}`, { title });
          if (text !== latest!.body_text) await post(`${base}/assets/${id}/versions`, { body: { ...latest!.body, edited: true }, body_text: text });
          setMode("read");
        }, "Saved a new version")}>Save changes</Button>}
        <CopyButton text={text} label="Copy" />
        <LinkButton href={downloadUrl(`${base}/${api}/work/${id}/export?format=md`)} download><Download className="h-4 w-4" />Markdown</LinkButton>
        <LinkButton href={downloadUrl(`${base}/${api}/work/${id}/export?format=html`)} download>HTML</LinkButton>
        {api === "freelancer" && <LinkButton href={downloadUrl(`${base}/${api}/work/${id}/export?format=txt`)} download>Plain text</LinkButton>}
        <span className="flex-1" />
        {canWrite && <ConfirmButton label="Delete this?" onConfirm={async () => { await del(`${base}/assets/${id}`); toast("Deleted"); onChanged(); onClose(); }}>Delete</ConfirmButton>}
      </div>}>
      {!a ? <p className="text-muted">Loading…</p> : (
        <div className="flex flex-col gap-5">
          <div className="text-[13px] text-muted">{label ? label(a) : tool(a.tags[0])?.title ?? a.type} · version {a.current_version} · updated {fmtDate(a.updated_at)} {fmtTime(a.updated_at)}</div>
          <Field label="Project" htmlFor="wp"><Select id="wp" disabled={!canWrite} value={a.project_id ?? ""} onChange={(e) =>
            act("move", () => patch(`${base}/${api}/work/${id}/project${e.target.value ? `?project_id=${e.target.value}` : ""}`, {}), "Moved")}>
            <option value="">No project</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
          {canWrite && <Tabs value={mode} onChange={setMode} items={[{ id: "read", label: "Read" }, { id: "edit", label: "Edit" }]} />}
          {mode === "read" ? <div className="rounded-m border border-line bg-raised p-4"><Markdown text={text} /></div> : <>
            <Field label="Title" htmlFor="wt"><Input id="wt" value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} /></Field>
            <Field label="Content" htmlFor="wb" hint="Markdown: ### headings, - bullets, **bold**"><Textarea id="wb" rows={18} value={text} onChange={(e) => setText(e.target.value)} className="font-mono text-[13px]" /></Field></>}
          <section>
            <h3 className="mb-2 flex items-center gap-2 text-[15px] font-semibold"><History className="h-4 w-4" />Versions</h3>
            <ul className="divide-y divide-line rounded-m border border-line bg-raised">
              {versions.data?.map((v) => <li key={v.id} className="flex items-center justify-between gap-2 px-3 py-2 text-[14px]">
                <span>v{v.version} · {v.source === "ai" ? "AI draft" : "Edited"} · {fmtDate(v.created_at)} {fmtTime(v.created_at)}</span>
                <Button variant="ghost" size="sm" onClick={() => setView(v)}>View</Button></li>)}
            </ul>
          </section>
        </div>)}
      {view && <Modal open onClose={() => setView(null)} title={`Version ${view.version}`}
        footer={canWrite && view.version !== latest?.version ? <Button onClick={() => { setText(view.body_text); setMode("edit"); setView(null); }}>Restore into editor</Button> : undefined}>
        <Markdown text={view.body_text || "(empty)"} /></Modal>}
    </Drawer>
  );
}
