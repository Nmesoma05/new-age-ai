"use client";
// Freelancer tools: one config-driven form, one result card with the actions each output supports.
import { Mic, Save, Wand2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { errorText, post, useApi } from "@/lib/api";
import type { ApplicationRow, FlTool, Opportunity } from "@/lib/fl";
import type { Exchange } from "@/lib/types";
import { RunPanel } from "../RunPanel";
import { useWs } from "../Shell";
import { Button, Card, CopyButton, Field, Input, LinkButton, Markdown, Modal, Select, Skeleton, Textarea, Toggle, useToast } from "../ui";

type Project = { id: string; name: string };
export const MARKETS = [["global_remote", "International remote"], ["us", "United States"], ["canada", "Canada"], ["uk", "United Kingdom"],
  ["europe", "Continental Europe"], ["middle_east", "Gulf / Middle East"], ["africa_local", "Local roles in Africa"]] as const;

export function useFlGenerate() {
  const { ws } = useWs();
  const [result, setResult] = useState<Exchange | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run(body: Record<string, unknown>) {
    setBusy(true); setError(""); setResult(null);
    try { setResult(await post<Exchange>(`/v1/workspaces/${ws.id}/freelancer/generate`, body)); }
    catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }
  return { run, result, busy, error };
}

export function Working({ label }: { label: string }) {
  return <Card className="flex flex-col gap-3" aria-busy="true">
    <div className="flex items-center gap-2 text-[14px] font-semibold"><Wand2 className="h-4 w-4 animate-pulse text-d3" />{label}</div>
    <Skeleton className="h-4 w-3/4" /><Skeleton className="h-4 w-2/3" /><Skeleton className="h-24 w-full" /></Card>;
}

export function FlToolForm({ def, onRun, busy, disabled, initial }: { def: FlTool; onRun: (b: Record<string, unknown>) => void; busy: boolean;
  disabled?: boolean; initial?: { opportunity?: string | null; application?: string | null } }) {
  const { ws } = useWs();
  const n = def.needs;
  const opps = useApi<Opportunity[]>(n.includes("opportunity") ? `/v1/workspaces/${ws.id}/freelancer/opportunities` : null);
  const apps = useApi<ApplicationRow[]>(n.includes("application") ? `/v1/workspaces/${ws.id}/freelancer/applications` : null);
  const [f, setF] = useState({ brief: "", job_text: "", opportunity_id: initial?.opportunity ?? "", application_id: initial?.application ?? "",
    target_role: "", market: "global_remote", letter_type: "cover_letter", platforms: ["linkedin"] as string[], weeks: 4, question_count: 6 });
  const needOpp = def.key === "opportunity";
  const ok = (!needOpp || f.opportunity_id) && (!n.includes("platforms") || f.platforms.length);
  return (
    <form className="flex flex-col gap-4" onSubmit={(e) => {
      e.preventDefault();
      const b: Record<string, unknown> = { tool: def.key, brief: f.brief };
      if (n.includes("job_text") && f.job_text.trim()) b.job_text = f.job_text;
      if (n.includes("opportunity") && f.opportunity_id) b.opportunity_id = f.opportunity_id;
      if (n.includes("application") && f.application_id) b.application_id = f.application_id;
      if (n.includes("target_role") && f.target_role.trim()) b.target_role = f.target_role;
      if (n.includes("market")) b.market = f.market;
      if (n.includes("letter_type")) b.letter_type = f.letter_type;
      if (n.includes("platforms")) b.platforms = f.platforms;
      if (n.includes("weeks")) b.weeks = f.weeks;
      if (n.includes("questions")) b.question_count = f.question_count;
      onRun(b);
    }}>
      {n.includes("letter_type") && <Field label="What are you writing?" htmlFor="lt"><Select id="lt" value={f.letter_type} onChange={(e) => setF({ ...f, letter_type: e.target.value })}>
        <option value="cover_letter">Cover letter (job)</option><option value="proposal">Proposal (freelance project)</option><option value="pitch_message">Short pitch message</option></Select></Field>}
      {n.includes("opportunity") && (
        <Field label={needOpp ? "Opportunity" : "From a saved opportunity (optional)"} htmlFor="op"><Select id="op" value={f.opportunity_id} onChange={(e) => setF({ ...f, opportunity_id: e.target.value })}>
          <option value="">{needOpp ? "Choose…" : "None"}</option>{opps.data?.map((o) => <option key={o.id} value={o.id}>{o.title}{o.organisation ? ` · ${o.organisation}` : ""}</option>)}</Select></Field>)}
      {n.includes("application") && (apps.data?.length ?? 0) > 0 && (
        <Field label="For an application (optional)" htmlFor="ap"><Select id="ap" value={f.application_id} onChange={(e) => setF({ ...f, application_id: e.target.value })}>
          <option value="">None</option>{apps.data?.map((a) => <option key={a.id} value={a.id}>{a.title}{a.organisation ? ` · ${a.organisation}` : ""}</option>)}</Select></Field>)}
      {n.includes("target_role") && <Field label="Target role" htmlFor="tr"><Input id="tr" value={f.target_role} maxLength={150} onChange={(e) => setF({ ...f, target_role: e.target.value })} placeholder="e.g. Product designer" /></Field>}
      {n.includes("market") && <Field label="Application conventions" htmlFor="mk" hint="Length, photo and personal details differ by country"><Select id="mk" value={f.market} onChange={(e) => setF({ ...f, market: e.target.value })}>
        {MARKETS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>}
      {n.includes("job_text") && <Field label="Paste the job post or brief (optional)" htmlFor="jt" hint="Treated as outside information, never as your experience">
        <Textarea id="jt" rows={5} maxLength={20000} value={f.job_text} onChange={(e) => setF({ ...f, job_text: e.target.value })} /></Field>}
      {n.includes("platforms") && <Field label="Platforms"><div className="flex flex-wrap gap-2" role="group" aria-label="Platforms">
        {["linkedin", "x", "instagram", "threads", "facebook", "tiktok"].map((p) => <Toggle key={p} on={f.platforms.includes(p)}
          onChange={(on) => setF({ ...f, platforms: on ? [...f.platforms, p] : f.platforms.filter((x) => x !== p) })}>{p === "x" ? "X" : p[0].toUpperCase() + p.slice(1)}</Toggle>)}</div></Field>}
      {n.includes("weeks") && <Field label="Plan length" htmlFor="wk"><Select id="wk" value={f.weeks} onChange={(e) => setF({ ...f, weeks: Number(e.target.value) })}>
        {[2, 4, 6, 8, 12].map((w) => <option key={w} value={w}>{w} weeks</option>)}</Select></Field>}
      {n.includes("questions") && <Field label="Number of questions" htmlFor="qc"><Select id="qc" value={f.question_count} onChange={(e) => setF({ ...f, question_count: Number(e.target.value) })}>
        {[4, 6, 8, 10].map((w) => <option key={w} value={w}>{w}</option>)}</Select></Field>}
      <Field label="Anything else? (optional)" htmlFor="br"><Textarea id="br" rows={3} maxLength={4000} value={f.brief} onChange={(e) => setF({ ...f, brief: e.target.value })} placeholder={def.placeholder} /></Field>
      <div><Button type="submit" ai loading={busy} disabled={disabled || !ok}>{def.button}</Button></div>
      {def.note && <p className="text-[13px] text-muted">{def.note}</p>}
    </form>
  );
}

function SaveModal({ runId, defTitle, onClose, onSaved }: { runId: string; defTitle: string; onClose: () => void; onSaved: (id: string) => void }) {
  const { ws } = useWs();
  const toast = useToast();
  const projects = useApi<{ data: Project[] }>(`/v1/workspaces/${ws.id}/projects?limit=50`);
  const [title, setTitle] = useState(defTitle);
  const [project, setProject] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Modal open onClose={onClose} title="Save to your work"
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={busy} disabled={!title.trim() || (project === "__new" && !name.trim())} onClick={async () => {
        setBusy(true);
        try {
          let pid: string | null = project && project !== "__new" ? project : null;
          if (project === "__new") pid = (await post<Project>(`/v1/workspaces/${ws.id}/projects`, { name: name.trim() })).id;
          const a = await post<{ id: string }>(`/v1/workspaces/${ws.id}/freelancer/runs/${runId}/save`, { title: title.trim(), project_id: pid });
          toast("Saved. You can edit it any time."); onSaved(a.id); onClose();
        } catch (e) { toast(errorText(e), "danger"); } finally { setBusy(false); }
      }}>Save</Button></>}>
      <div className="flex flex-col gap-4">
        <Field label="Title" htmlFor="sv-t"><Input id="sv-t" value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} /></Field>
        <Field label="Project" htmlFor="sv-p" hint="e.g. 'Job hunt: design roles' or a client's name"><Select id="sv-p" value={project} onChange={(e) => setProject(e.target.value)}>
          <option value="">No project</option>{projects.data?.data.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}<option value="__new">New project…</option></Select></Field>
        {project === "__new" && <Field label="New project name" htmlFor="sv-n"><Input id="sv-n" value={name} onChange={(e) => setName(e.target.value)} /></Field>}
      </div>
    </Modal>
  );
}

export function FlToolResult({ ex, def, onApplied }: { ex: Exchange; def: FlTool; onApplied?: () => void }) {
  const { ws, base, canWrite } = useWs();
  const toast = useToast();
  const run = ex.run;
  const ok = run.status === "succeeded" && !!run.output;
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState("");
  return (
    <Card className="flex flex-col gap-4 animate-rise">
      <RunPanel run={run} />
      <Markdown text={ex.assistant_message.content} />
      {ok && canWrite && (
        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
          {saved ? <LinkButton href={`${base}/work?open=${saved}`}>Open saved copy</LinkButton>
            : <Button icon={<Save className="h-4 w-4" />} onClick={() => setSaving(true)}>Save</Button>}
          {def.key === "assessment" && <Button variant="secondary" loading={busy === "apply"} onClick={async () => {
            setBusy("apply");
            try { await post(`/v1/workspaces/${ws.id}/freelancer/runs/${run.id}/apply-assessment`); toast("Added to your profile"); onApplied?.(); }
            catch (e) { toast(errorText(e), "danger"); } finally { setBusy(""); }
          }}>Use as my assessment</Button>}
          {def.key === "interview" && <Button variant="secondary" icon={<Mic className="h-4 w-4" />} loading={busy === "mock"} onClick={async () => {
            setBusy("mock");
            try {
              const s = await post<{ id: string }>(`/v1/workspaces/${ws.id}/freelancer/interviews`, { role_title: String(run.output?.role || "Interview"), run_id: run.id });
              location.href = `${base}/interview/${s.id}`;
            } catch (e) { toast(errorText(e), "danger"); setBusy(""); }
          }}>Practise these questions</Button>}
          <CopyButton text={ex.assistant_message.content} label="Copy" />
        </div>)}
      {!ok && <p className="text-[13px] text-muted">Nothing to save from this one. <Link className="underline" href={`${base}/profile`}>Add more to your profile</Link> or try again.</p>}
      {saving && <SaveModal runId={run.id} defTitle={`${def.title} · ${new Date().toISOString().slice(0, 10)}`} onClose={() => setSaving(false)} onSaved={setSaved} />}
    </Card>
  );
}
