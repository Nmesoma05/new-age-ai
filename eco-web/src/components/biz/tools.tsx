"use client";
// Business strategy tools: one config-driven form and one result view with the actions each output supports.
import { Megaphone, Save, ShieldCheck, Wand2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { downloadUrl, errorText, post, useApi } from "@/lib/api";
import { SOCIAL, type Project, type ToolDef } from "@/lib/biz";
import type { Exchange } from "@/lib/types";
import { RunPanel } from "../RunPanel";
import { useWs } from "../Shell";
import { Button, Card, CopyButton, Field, Input, LinkButton, Markdown, Modal, Notice, Select, Skeleton, Textarea, Toggle, useToast } from "../ui";

export function useBizGenerate() {
  const { ws } = useWs();
  const [result, setResult] = useState<Exchange | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run(body: Record<string, unknown>) {
    setBusy(true); setError(""); setResult(null);
    try { setResult(await post<Exchange>(`/v1/workspaces/${ws.id}/business/generate`, body)); }
    catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }
  return { run, result, busy, error, setResult };
}

export function Thinking({ label }: { label: string }) {
  return (
    <Card className="flex flex-col gap-3" aria-busy="true">
      <div className="flex items-center gap-2 text-[14px] font-semibold"><Wand2 className="h-4 w-4 animate-pulse text-d2" />{label}</div>
      <Skeleton className="h-4 w-3/4" /><Skeleton className="h-4 w-2/3" /><Skeleton className="h-24 w-full" />
    </Card>
  );
}

const iso = (d: Date) => d.toISOString().slice(0, 10);
const addDays = (n: number) => { const d = new Date(); d.setDate(d.getDate() + n); return iso(d); };

export function ToolForm({ def, onRun, busy, disabled }: { def: ToolDef; onRun: (b: Record<string, unknown>) => void; busy: boolean; disabled?: boolean }) {
  const isReport = def.key === "report";
  const [brief, setBrief] = useState("");
  const [months, setMonths] = useState(3);
  const [platforms, setPlatforms] = useState<string[]>(["instagram", "whatsapp"]);
  const [start, setStart] = useState(isReport ? addDays(-29) : addDays(7));
  const [end, setEnd] = useState(isReport ? iso(new Date()) : addDays(37));
  const needs = def.needs ?? [];
  const datesOk = !needs.includes("dates") || (start && end && end >= start);
  return (
    <form className="flex flex-col gap-4" onSubmit={(e) => {
      e.preventDefault();
      onRun({ tool: def.key, brief, ...(needs.includes("months") ? { plan_months: months } : {}),
        ...(needs.includes("platforms") ? { platforms } : {}), ...(needs.includes("dates") ? { start_date: start, end_date: end } : {}) });
    }}>
      <Field label="What do you want from this? (optional)" htmlFor="brief">
        <Textarea id="brief" rows={3} value={brief} onChange={(e) => setBrief(e.target.value)} placeholder={def.placeholder} maxLength={4000} /></Field>
      {needs.includes("months") && (
        <Field label="Plan length" htmlFor="months"><Select id="months" value={months} onChange={(e) => setMonths(Number(e.target.value))}>
          {[1, 2, 3, 6, 12].map((m) => <option key={m} value={m}>{m} month{m > 1 ? "s" : ""}</option>)}</Select></Field>)}
      {needs.includes("platforms") && (
        <Field label="Platforms">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Platforms">
            {SOCIAL.map((p) => <Toggle key={p} on={platforms.includes(p)} onChange={(on) => setPlatforms(on ? [...platforms, p] : platforms.filter((x) => x !== p))}>
              {p === "x" ? "X" : p[0].toUpperCase() + p.slice(1)}</Toggle>)}
          </div></Field>)}
      {needs.includes("dates") && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={isReport ? "From" : "Campaign starts"} htmlFor="sd"><Input id="sd" type="date" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
          <Field label={isReport ? "To" : "Campaign ends"} htmlFor="ed" error={datesOk ? undefined : "End must be after start"}><Input id="ed" type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
        </div>)}
      <div><Button type="submit" ai loading={busy} disabled={disabled || !datesOk || (needs.includes("platforms") && !platforms.length)}>{def.button}</Button></div>
      {disabled && <p className="text-[13px] text-muted">Your role can view this business but can't run the AI.</p>}
    </form>
  );
}

function SaveModal({ runId, defTitle, onClose, onSaved }: { runId: string; defTitle: string; onClose: () => void; onSaved: (id: string) => void }) {
  const { ws } = useWs();
  const toast = useToast();
  const projects = useApi<{ data: Project[] } | Project[]>(`/v1/workspaces/${ws.id}/projects?limit=50`);
  const list = Array.isArray(projects.data) ? projects.data : projects.data?.data ?? [];
  const [title, setTitle] = useState(defTitle);
  const [project, setProject] = useState("");
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Modal open onClose={onClose} title="Save to your work"
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={busy} disabled={!title.trim() || (project === "__new" && !newName.trim())} onClick={async () => {
        setBusy(true);
        try {
          let pid: string | null = project && project !== "__new" ? project : null;
          if (project === "__new") pid = (await post<Project>(`/v1/workspaces/${ws.id}/projects`, { name: newName.trim() })).id;
          const a = await post<{ id: string }>(`/v1/workspaces/${ws.id}/business/runs/${runId}/save`, { title: title.trim(), project_id: pid });
          toast("Saved. You can edit it any time."); onSaved(a.id); onClose();
        } catch (e) { toast(errorText(e), "danger"); } finally { setBusy(false); }
      }}>Save</Button></>}>
      <div className="flex flex-col gap-4">
        <Field label="Title" htmlFor="svt"><Input id="svt" value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} /></Field>
        <Field label="Project" htmlFor="svp" hint="Group related work, like a launch or a season"><Select id="svp" value={project} onChange={(e) => setProject(e.target.value)}>
          <option value="">No project</option>{list.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}<option value="__new">New project…</option></Select></Field>
        {project === "__new" && <Field label="New project name" htmlFor="svn"><Input id="svn" value={newName} onChange={(e) => setNewName(e.target.value)} /></Field>}
      </div>
    </Modal>
  );
}

function SpendModal({ runId, title, onClose }: { runId: string; title: string; onClose: () => void }) {
  const { ws, base } = useWs();
  const toast = useToast();
  const [f, setF] = useState({ amount: "", currency: "NGN", notes: "" });
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  return (
    <Modal open onClose={onClose} title="Request approval to spend"
      footer={done ? <LinkButton href={`${base}/approvals`}>See approvals</LinkButton> : <><Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button loading={busy} disabled={!(Number(f.amount) > 0) || !/^[A-Z]{3}$/.test(f.currency)} onClick={async () => {
          setBusy(true);
          try {
            await post(`/v1/workspaces/${ws.id}/business/approvals`, { kind: "spend_money", run_id: runId, title: `Launch: ${title}`.slice(0, 200),
              amount: f.amount, currency: f.currency, notes: f.notes });
            setDone(true); toast("Approval requested");
          } catch (e) { toast(errorText(e), "danger"); } finally { setBusy(false); }
        }}>Request approval</Button></>}>
      {done ? <Notice tone="success" title="Request recorded">An owner or admin can approve or reject it. No ad account is connected, so nothing will be launched or paid even after approval: you run the ads yourself and record the results.</Notice> : (
        <div className="flex flex-col gap-4">
          <Notice tone="warning">This only records a request. Nothing is launched or paid from here.</Notice>
          <div className="grid gap-4 sm:grid-cols-[1fr_110px]">
            <Field label="Amount to spend" htmlFor="spa"><Input id="spa" type="number" min={1} value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
            <Field label="Currency" htmlFor="spc"><Input id="spc" maxLength={3} value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value.toUpperCase() })} /></Field>
          </div>
          <Field label="Notes for the approver" htmlFor="spn"><Textarea id="spn" rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
        </div>)}
    </Modal>
  );
}

export function ToolResult({ ex, def, params, onApplied }: { ex: Exchange; def: ToolDef; params?: Record<string, unknown>; onApplied?: () => void }) {
  const { ws, base, canWrite } = useWs();
  const toast = useToast();
  const run = ex.run;
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [spend, setSpend] = useState(false);
  const [busy, setBusy] = useState("");
  const [parts, setParts] = useState<string[]>(["positioning", "messages", "voice"]);
  const ok = run.status === "succeeded" && !!run.output;
  async function act(label: string, fn: () => Promise<unknown>, msg: string) {
    setBusy(label);
    try { await fn(); toast(msg); onApplied?.(); } catch (e) { toast(errorText(e), "danger"); } finally { setBusy(""); }
  }
  return (
    <Card className="flex flex-col gap-4 animate-rise">
      <RunPanel run={run} />
      <Markdown text={ex.assistant_message.content} />
      {ok && canWrite && (
        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
          {saved ? <LinkButton href={`${base}/work?open=${saved}`}>Open saved copy</LinkButton>
            : <Button icon={<Save className="h-4 w-4" />} onClick={() => setSaving(true)}>Save</Button>}
          {def.key === "intelligence" && <Button variant="secondary" loading={busy === "apply"}
            onClick={() => act("apply", () => post(`/v1/workspaces/${ws.id}/business/runs/${run.id}/apply-intelligence`), "Profile updated")}>Use as my profile</Button>}
          {def.key === "ads" && <>
            <Button variant="secondary" icon={<Megaphone className="h-4 w-4" />} loading={busy === "camp"} onClick={() => act("camp", async () => {
              const c = await post<{ id: string }>(`/v1/workspaces/${ws.id}/business/runs/${run.id}/create-campaign`);
              location.href = `${base}/campaigns?open=${c.id}`;
            }, "Campaign created")}>Create campaign</Button>
            <Button variant="secondary" icon={<ShieldCheck className="h-4 w-4" />} onClick={() => setSpend(true)}>Request approval to spend</Button></>}
          {def.key === "report" && <>
            <LinkButton href={downloadUrl(`/v1/workspaces/${ws.id}/business/report/export?format=html&start=${params?.start_date}&end=${params?.end_date}&run_id=${run.id}`)} download>Download report (HTML)</LinkButton>
            <LinkButton href={downloadUrl(`/v1/workspaces/${ws.id}/business/report/export?format=md&start=${params?.start_date}&end=${params?.end_date}&run_id=${run.id}`)} download>Markdown</LinkButton></>}
          <CopyButton text={ex.assistant_message.content} label="Copy" />
        </div>)}
      {ok && canWrite && def.key === "positioning" && (
        <div className="flex flex-col gap-2 rounded-m bg-sunken p-3">
          <div className="text-[14px] font-semibold">Apply to your profile's brand section</div>
          <div className="flex flex-wrap gap-2">{[["positioning", "Positioning"], ["messages", "Messages & taglines"], ["voice", "Personality & tone"], ["visual", "Visual direction"]].map(([k, l]) => (
            <Toggle key={k} on={parts.includes(k)} onChange={(on) => setParts(on ? [...parts, k] : parts.filter((x) => x !== k))}>{l}</Toggle>))}</div>
          <div><Button variant="secondary" size="sm" disabled={!parts.length} loading={busy === "pos"}
            onClick={() => act("pos", () => post(`/v1/workspaces/${ws.id}/business/runs/${run.id}/apply-positioning`, { parts }), "Applied to your profile")}>Apply selected</Button></div>
        </div>)}
      {saving && <SaveModal runId={run.id} defTitle={`${def.title} · ${new Date().toISOString().slice(0, 10)}`} onClose={() => setSaving(false)} onSaved={setSaved} />}
      {spend && <SpendModal runId={run.id} title={String(run.output?.objective ?? def.title)} onClose={() => setSpend(false)} />}
      {ok && !canWrite && <p className="text-[13px] text-muted">Viewers can read results but not save them.</p>}
      {!ok && <p className="text-[13px] text-muted">Nothing to save from this one. <Link className="underline" href={`${base}/strategist`}>Ask the strategist</Link> if you're stuck.</p>}
    </Card>
  );
}
