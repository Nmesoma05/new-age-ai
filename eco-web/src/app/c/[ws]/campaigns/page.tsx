"use client";
import { Megaphone, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { errorText, post, useApi } from "@/lib/api";
import type { Campaign, ClientProfile, Platform } from "@/lib/types";
import { platformLabel } from "@/lib/types";
import { PlatformPicker } from "@/components/PlatformPicker";
import { useWs } from "@/components/Shell";
import { CampaignForm, CampaignResult, Generating, useGenerate } from "@/components/studio";
import { Badge, Button, EmptyState, Field, Input, Modal, Notice, PageHeader, StatusBadge, Textarea, fmtDate, useToast } from "@/components/ui";

export default function Campaigns() {
  const { ws, base, canWrite } = useWs();
  const router = useRouter();
  const list = useApi<Campaign[]>(`/v1/workspaces/${ws.id}/creator/campaigns`);
  const profile = useApi<ClientProfile>(`/v1/workspaces/${ws.id}/client-account`);
  const [ai, setAi] = useState(false);
  const [manual, setManual] = useState(false);
  const g = useGenerate();
  return (
    <div>
      <PageHeader title="Campaigns" description="Plan launches and pushes with phases, channels and deliverables, then fill the calendar.">
        <Button variant="secondary" icon={<Plus className="h-4 w-4" />} disabled={!canWrite} onClick={() => setManual(true)}>New campaign</Button>
        <Button ai disabled={!canWrite} onClick={() => setAi(true)}>Plan with AI</Button>
      </PageHeader>
      {list.data?.length === 0 && <EmptyState icon={<Megaphone className="h-6 w-6" />} title="No campaigns yet">Plan one with AI or set one up yourself.</EmptyState>}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {list.data?.map((c) => (
          <a key={c.id} href={`${base}/campaigns/${c.id}`} className="flex flex-col gap-3 rounded-m border border-line bg-raised p-5 transition hover:-translate-y-0.5 hover:border-control hover:shadow-1">
            <div className="flex items-center justify-between gap-2"><StatusBadge status={c.status} />
              <span className="font-mono text-[12px] text-muted">{c.start_date ? `${fmtDate(c.start_date)} – ${c.end_date ? fmtDate(c.end_date) : "…"}` : "No dates"}</span></div>
            <div className="text-[18px] font-semibold">{c.name}</div>
            {c.objective && <p className="line-clamp-2 text-[14px] text-muted">{c.objective}</p>}
            <div className="flex flex-wrap gap-1.5">{c.channels.map((ch) => <Badge key={ch} tone="d1">{platformLabel(ch)}</Badge>)}{c.source_run_id && <Badge tone="orange">AI plan</Badge>}</div>
          </a>))}
      </div>
      <Modal open={ai} wide onClose={() => { setAi(false); g.setResult(null); }} title="Plan a campaign with AI">
        {!g.result && !g.busy && <CampaignForm onRun={g.run} busy={g.busy} platforms={profile.data?.platforms ?? []} />}
        {g.error && <div className="mt-3"><Notice tone="danger">{g.error}</Notice></div>}
        {g.busy && <Generating label="Planning the campaign…" />}
        {g.result && (g.result.run.status === "succeeded" ? <CampaignResult ex={g.result} onCreated={(id) => router.push(`${base}/campaigns/${id}`)} />
          : <Notice tone="warning">{g.result.assistant_message.content}</Notice>)}
      </Modal>
      {manual && <ManualModal onClose={() => setManual(false)} onCreated={(id) => router.push(`${base}/campaigns/${id}`)} />}
    </div>
  );
}

function ManualModal({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const { ws } = useWs();
  const toast = useToast();
  const [f, setF] = useState({ name: "", objective: "", start_date: "", end_date: "", channels: [] as Platform[], budget_note: "" });
  const [busy, setBusy] = useState(false);
  return (
    <Modal open onClose={onClose} title="New campaign" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button>
      <Button loading={busy} disabled={!f.name.trim() || (!!f.end_date && !!f.start_date && f.end_date < f.start_date)} onClick={async () => {
        setBusy(true);
        try { const c = await post<Campaign>(`/v1/workspaces/${ws.id}/creator/campaigns`, { ...f, start_date: f.start_date || null, end_date: f.end_date || null }); onCreated(c.id); }
        catch (e) { toast(errorText(e), "danger"); setBusy(false); }
      }}>Create</Button></>}>
      <div className="flex flex-col gap-4">
        <Field label="Name" htmlFor="cn"><Input id="cn" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Objective" htmlFor="co"><Textarea id="co" rows={2} value={f.objective} onChange={(e) => setF({ ...f, objective: e.target.value })} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Starts" htmlFor="cs"><Input id="cs" type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></Field>
          <Field label="Ends" htmlFor="ce"><Input id="ce" type="date" value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} /></Field>
        </div>
        <Field label="Channels"><PlatformPicker value={f.channels} onChange={(c) => setF({ ...f, channels: c })} /></Field>
        <Field label="Budget note" htmlFor="cb"><Input id="cb" value={f.budget_note} onChange={(e) => setF({ ...f, budget_note: e.target.value })} /></Field>
      </div>
    </Modal>
  );
}
