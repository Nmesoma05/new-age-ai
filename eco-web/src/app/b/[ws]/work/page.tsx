"use client";
import { FolderOpen, FolderPlus } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { errorText, post, useApi } from "@/lib/api";
import { TOOLS, tool, type Project } from "@/lib/biz";
import type { Asset } from "@/lib/types";
import { WorkDrawer } from "@/components/biz/WorkDrawer";
import { useWs } from "@/components/Shell";
import { Button, EmptyState, Field, Input, Modal, PageHeader, Select, Skeleton, cx, fmtDate, useToast } from "@/components/ui";

export default function Work() {
  const { ws, base, canWrite } = useWs();
  const toast = useToast();
  const router = useRouter();
  const search = useSearchParams();
  const open = search.get("open");
  const [project, setProject] = useState<string>("");
  const [type, setType] = useState("");
  const [newOpen, setNewOpen] = useState(false);
  const [name, setName] = useState("");
  const projects = useApi<{ data: Project[] } | Project[]>(`/v1/workspaces/${ws.id}/projects?limit=50`);
  const plist = Array.isArray(projects.data) ? projects.data : projects.data?.data ?? [];
  const q = new URLSearchParams();
  if (project === "__none") q.set("unfiled", "true"); else if (project) q.set("project_id", project);
  if (type) q.set("type", type);
  const work = useApi<(Asset & { project_id: string | null })[]>(`/v1/workspaces/${ws.id}/business/work?${q}`);
  const types = Array.from(new Set(TOOLS.map((t) => t.key)));
  const setOpen = (id: string | null) => router.replace(id ? `${base}/work?open=${id}` : `${base}/work`);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Saved work" description="Plans, strategies and reports you've saved. Group them into projects, edit them and export them.">
        {canWrite && <Button variant="secondary" icon={<FolderPlus className="h-4 w-4" />} onClick={() => setNewOpen(true)}>New project</Button>}
      </PageHeader>
      <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
        <nav aria-label="Projects" className="flex flex-row gap-1 overflow-x-auto lg:flex-col">
          {[{ id: "", name: "All work" }, ...plist, { id: "__none", name: "Not in a project" }].map((p) => (
            <button key={p.id} onClick={() => setProject(p.id)} className={cx("flex min-h-[40px] shrink-0 items-center gap-2 rounded-m px-3 text-left text-[14px] font-semibold",
              project === p.id ? "bg-d2-soft text-d2" : "hover:bg-sunken")}><FolderOpen className="h-4 w-4" />{p.name}</button>))}
        </nav>
        <div className="flex min-w-0 flex-col gap-3">
          <div className="flex items-end gap-2"><Field label="Type" htmlFor="wtype"><Select id="wtype" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">All types</option>{[...new Set(TOOLS.map((t) => assetType(t.key)))].map((t) => <option key={t} value={t}>{typeLabel(t)}</option>)}</Select></Field></div>
          {!work.data && <Skeleton className="h-40" />}
          {work.data?.length === 0 && <EmptyState tone="d2" icon={<FolderOpen className="h-6 w-6" />} title="Nothing here yet"
            action={<Link className="font-semibold text-orange-text underline" href={`${base}/tools`}>Open the strategy tools</Link>}>Save any tool's result and it appears here.</EmptyState>}
          <ul className="grid gap-3 sm:grid-cols-2">
            {work.data?.map((a) => (
              <li key={a.id}><button onClick={() => setOpen(a.id)} className="flex w-full flex-col rounded-m border border-line bg-raised p-4 text-left transition hover:border-control hover:shadow-1">
                <span className="text-[12px] font-semibold uppercase tracking-[0.6px] text-d2">{tool(a.tags[0])?.title ?? typeLabel(a.type)}</span>
                <span className="mt-1 font-semibold">{a.title}</span>
                <span className="mt-2 text-[13px] text-muted">{plist.find((p) => p.id === a.project_id)?.name ?? "No project"} · v{a.current_version} · {fmtDate(a.updated_at)}</span>
              </button></li>))}
          </ul>
          {types.length === 0 && null}
        </div>
      </div>
      {open && <WorkDrawer id={open} projects={plist} onClose={() => setOpen(null)} onChanged={work.reload} />}
      <Modal open={newOpen} onClose={() => setNewOpen(false)} title="New project"
        footer={<><Button variant="ghost" onClick={() => setNewOpen(false)}>Cancel</Button><Button disabled={!name.trim()} onClick={async () => {
          try { const p = await post<Project>(`/v1/workspaces/${ws.id}/projects`, { name: name.trim() }); toast("Project created"); setName(""); setNewOpen(false); projects.reload(); setProject(p.id); }
          catch (e) { toast(errorText(e), "danger"); }
        }}>Create</Button></>}>
        <Field label="Project name" htmlFor="npn" hint="e.g. December push, New branch launch"><Input id="npn" value={name} onChange={(e) => setName(e.target.value)} /></Field>
      </Modal>
    </div>
  );
}

const ASSET: Record<string, string> = { intelligence: "intelligence_profile", positioning: "positioning", market: "research",
  competitors: "competitor_analysis", plan: "marketing_plan", content: "content_plan", ads: "ad_plan", acquisition: "growth_plan",
  retention: "growth_plan", report: "report" };
const LABEL: Record<string, string> = { intelligence_profile: "Intelligence profiles", positioning: "Positioning", research: "Research",
  competitor_analysis: "Competitor analyses", marketing_plan: "Marketing plans", content_plan: "Content plans", ad_plan: "Ad plans",
  growth_plan: "Growth plans", report: "Reports" };
const assetType = (k: string) => ASSET[k];
const typeLabel = (t: string) => LABEL[t] ?? t;
