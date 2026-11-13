"use client";
import { FileUp, FolderOpen, FolderPlus } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { api, del, errorText, post, useApi } from "@/lib/api";
import { ASSET_LABEL } from "@/lib/fl";
import type { Asset } from "@/lib/types";
import { WorkDrawer } from "@/components/biz/WorkDrawer";
import { useWs } from "@/components/Shell";
import { Badge, Button, ConfirmButton, EmptyState, Field, Input, Modal, Notice, PageHeader, Select, Skeleton, Tabs, cx, fmtDate, useToast } from "@/components/ui";

import type { Project } from "@/lib/biz";
type Doc = { id: string; filename: string; content_type: string; size_bytes: number; scan_status: string; text_status: string; created_at: string };

function Files() {
  const { ws, canWrite } = useWs();
  const toast = useToast();
  const docs = useApi<{ data: Doc[] }>(`/v1/workspaces/${ws.id}/documents?limit=50`);
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex flex-col gap-4">
      <Notice>Upload an old CV, certificates or a job brief (PDF, Word, text or image; up to the size limit). Readable text can be used by the AI when you ask, for example "use my uploaded CV". Files are checked before they can be downloaded.</Notice>
      {canWrite && <div><input ref={input} type="file" className="hidden" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg" onChange={async (e) => {
        const f = e.target.files?.[0]; if (!f) return;
        const fd = new FormData(); fd.append("file", f); setBusy(true);
        try { await api.upload(`/v1/workspaces/${ws.id}/documents`, fd); toast("Uploaded"); docs.reload(); } catch (x) { toast(errorText(x), "danger"); }
        finally { setBusy(false); e.target.value = ""; }
      }} /><Button icon={<FileUp className="h-4 w-4" />} loading={busy} onClick={() => input.current?.click()}>Upload a file</Button></div>}
      {!docs.data && <Skeleton className="h-24" />}
      {docs.data?.data.length === 0 && <p className="text-[14px] text-muted">No files yet.</p>}
      <ul className="divide-y divide-line rounded-m border border-line bg-raised">{docs.data?.data.map((d) => (
        <li key={d.id} className="flex flex-wrap items-center gap-3 p-3">
          <span className="min-w-0 flex-1 truncate font-semibold">{d.filename}</span>
          <span className="text-[13px] text-muted">{(d.size_bytes / 1024).toFixed(0)} KB · {fmtDate(d.created_at)}</span>
          <Badge tone={d.scan_status === "clean" ? "success" : d.scan_status === "rejected" ? "danger" : "warning"}>{d.scan_status === "clean" ? "Checked" : d.scan_status}</Badge>
          {d.text_status === "ready" && <Badge tone="d3">AI can read it</Badge>}
          {d.scan_status === "clean" && <Button size="sm" variant="ghost" onClick={async () => {
            try { const r = await post<{ url: string }>(`/v1/workspaces/${ws.id}/documents/${d.id}/download-url`); window.open(`/api/proxy${new URL(r.url).pathname}`, "_blank", "noopener"); }
            catch (x) { toast(errorText(x), "danger"); }
          }}>Download</Button>}
          {canWrite && <ConfirmButton label="Delete?" onConfirm={async () => { await del(`/v1/workspaces/${ws.id}/documents/${d.id}`); toast("Deleted"); docs.reload(); }}>Delete</ConfirmButton>}
        </li>))}</ul>
    </div>
  );
}

export default function FlWork() {
  const { ws, base, canWrite } = useWs();
  const toast = useToast();
  const router = useRouter();
  const sp = useSearchParams();
  const open = sp.get("open");
  const [tab, setTab] = useState<"work" | "files">(sp.get("tab") === "files" ? "files" : "work");
  const [project, setProject] = useState("");
  const [type, setType] = useState("");
  const [newOpen, setNewOpen] = useState(false);
  const [name, setName] = useState("");
  const projects = useApi<{ data: Project[] }>(`/v1/workspaces/${ws.id}/projects?limit=50`);
  const plist = projects.data?.data ?? [];
  const q = new URLSearchParams();
  if (project) q.set("project_id", project);
  if (type) q.set("type", type);
  const work = useApi<(Asset & { project_id: string | null })[]>(`/v1/workspaces/${ws.id}/freelancer/work?${q}`);
  const setOpen = (id: string | null) => router.replace(id ? `${base}/work?open=${id}` : `${base}/work`);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Saved work" description="Your CVs, letters, case studies and plans, with versions and exports, plus files you've uploaded.">
        {canWrite && tab === "work" && <Button variant="secondary" icon={<FolderPlus className="h-4 w-4" />} onClick={() => setNewOpen(true)}>New project</Button>}
      </PageHeader>
      <Tabs value={tab} onChange={setTab} items={[{ id: "work", label: "Documents I've made" }, { id: "files", label: "Uploaded files" }]} />
      {tab === "files" ? <Files /> : (
        <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
          <nav aria-label="Projects" className="flex flex-row gap-1 overflow-x-auto lg:flex-col">
            {[{ id: "", name: "Everything" }, ...plist].map((p) => <button key={p.id} onClick={() => setProject(p.id)}
              className={cx("flex min-h-[40px] shrink-0 items-center gap-2 rounded-m px-3 text-left text-[14px] font-semibold", project === p.id ? "bg-d3-soft text-d3" : "hover:bg-sunken")}>
              <FolderOpen className="h-4 w-4" />{p.name}</button>)}
          </nav>
          <div className="flex min-w-0 flex-col gap-3">
            <div className="w-56"><Field label="Type" htmlFor="ft"><Select id="ft" value={type} onChange={(e) => setType(e.target.value)}>
              <option value="">All types</option>{Object.entries(ASSET_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field></div>
            {!work.data && <Skeleton className="h-40" />}
            {work.data?.length === 0 && <EmptyState tone="d3" icon={<FolderOpen className="h-6 w-6" />} title="Nothing saved here yet"
              action={<Link className="font-semibold text-orange-text underline" href={`${base}/tools/cv`}>Build a CV</Link>}>Save any tool's result and it appears here.</EmptyState>}
            <ul className="grid gap-3 sm:grid-cols-2">{work.data?.map((a) => (
              <li key={a.id}><button onClick={() => setOpen(a.id)} className="flex w-full flex-col rounded-m border border-line bg-raised p-4 text-left transition hover:border-control hover:shadow-1">
                <span className="text-[12px] font-semibold uppercase tracking-[0.6px] text-d3">{ASSET_LABEL[a.type] ?? a.type}</span>
                <span className="mt-1 font-semibold">{a.title}</span>
                <span className="mt-2 text-[13px] text-muted">{plist.find((p) => p.id === a.project_id)?.name ?? "No project"} · v{a.current_version} · {fmtDate(a.updated_at)}</span>
              </button></li>))}</ul>
          </div>
        </div>)}
      {open && <WorkDrawer id={open} projects={plist} api="freelancer" label={(a) => ASSET_LABEL[a.type] ?? a.type} onClose={() => setOpen(null)} onChanged={work.reload} />}
      <Modal open={newOpen} onClose={() => setNewOpen(false)} title="New project"
        footer={<><Button variant="ghost" onClick={() => setNewOpen(false)}>Cancel</Button><Button disabled={!name.trim()} onClick={async () => {
          try { const p = await post<Project>(`/v1/workspaces/${ws.id}/projects`, { name: name.trim() }); toast("Project created"); setName(""); setNewOpen(false); projects.reload(); setProject(p.id); }
          catch (e) { toast(errorText(e), "danger"); }
        }}>Create</Button></>}>
        <Field label="Project name" htmlFor="pn" hint="e.g. Job hunt: design roles, or a client's name"><Input id="pn" value={name} onChange={(e) => setName(e.target.value)} /></Field>
      </Modal>
    </div>
  );
}
