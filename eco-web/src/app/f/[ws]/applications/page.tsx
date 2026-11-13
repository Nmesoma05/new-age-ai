"use client";
import { ClipboardList, ExternalLink, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { del, errorText, patch, post, useApi } from "@/lib/api";
import { APP_STATUSES, type ApplicationRow } from "@/lib/fl";
import type { Asset } from "@/lib/types";
import { useWs } from "@/components/Shell";
import { Button, ConfirmButton, Drawer, EmptyState, Field, Input, LinkButton, Modal, Notice, PageHeader, Select, Skeleton,
  StatusBadge, Tabs, Textarea, cx, fmtDate, useToast } from "@/components/ui";

const LABEL: Record<string, string> = { preparing: "Preparing", applied: "Applied", interviewing: "Interviewing", offer: "Offer",
  accepted: "Accepted", rejected: "Rejected", withdrawn: "Withdrawn", no_response: "No response" };
const ACTIVE = ["preparing", "applied", "interviewing", "offer"];

function Detail({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const { ws, base, canWrite } = useWs();
  const toast = useToast();
  const all = useApi<ApplicationRow[]>(`/v1/workspaces/${ws.id}/freelancer/applications`);
  const cvs = useApi<Asset[]>(`/v1/workspaces/${ws.id}/freelancer/work?type=cv`);
  const letters = useApi<Asset[]>(`/v1/workspaces/${ws.id}/freelancer/work?type=cover_letter`);
  const proposals = useApi<Asset[]>(`/v1/workspaces/${ws.id}/freelancer/work?type=proposal`);
  const a = all.data?.find((x) => x.id === id);
  const [f, setF] = useState<Partial<ApplicationRow> & { status_note?: string }>({});
  useEffect(() => { if (a) setF({ ...a, status_note: "" }); }, [a]);
  const [busy, setBusy] = useState(false);
  if (!a) return <Drawer open onClose={onClose} title="Application"><Skeleton className="h-64" /></Drawer>;
  const dirty = JSON.stringify({ ...a, status_note: "" }) !== JSON.stringify(f);
  return (
    <Drawer open onClose={onClose} title={a.title}
      footer={canWrite && <div className="flex w-full flex-wrap gap-2">
        <Button disabled={!dirty} loading={busy} onClick={async () => {
          setBusy(true);
          try {
            const body: Record<string, unknown> = {};
            for (const k of ["title", "organisation", "status", "next_step", "contact", "expected_pay", "notes"] as const)
              if (f[k] !== a[k]) body[k] = f[k];
            for (const k of ["next_step_due", "applied_on", "cv_asset_id", "letter_asset_id"] as const)
              if ((f[k] || null) !== a[k]) body[k] = f[k] || null;
            if (body.status && f.status_note) body.status_note = f.status_note;
            await patch(`/v1/workspaces/${ws.id}/freelancer/applications/${id}`, body);
            toast("Saved"); all.reload(); onChanged();
          } catch (e) { toast(errorText(e), "danger"); } finally { setBusy(false); }
        }}>Save changes</Button>
        <LinkButton href={`${base}/tools/interview?application=${id}`}>Prepare interview</LinkButton>
        <LinkButton href={`${base}/tools/proposal?application=${id}`}>Write letter</LinkButton>
        <span className="flex-1" />
        <ConfirmButton label="Delete this?" onConfirm={async () => { await del(`/v1/workspaces/${ws.id}/freelancer/applications/${id}`); toast("Deleted"); onChanged(); onClose(); }}>Delete</ConfirmButton>
      </div>}>
      <div className="flex flex-col gap-4">
        {a.url && <a href={a.url} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-1 text-[14px] font-semibold text-orange-text underline">Original posting<ExternalLink className="h-4 w-4" /></a>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Status" htmlFor="as"><Select id="as" disabled={!canWrite} value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
            {APP_STATUSES.map((s) => <option key={s} value={s}>{LABEL[s]}</option>)}</Select></Field>
          {f.status !== a.status && <Field label="Note about this change (optional)" htmlFor="asn"><Input id="asn" value={f.status_note} onChange={(e) => setF({ ...f, status_note: e.target.value })} /></Field>}
          <Field label="Next step" htmlFor="ans"><Input id="ans" disabled={!canWrite} value={f.next_step ?? ""} onChange={(e) => setF({ ...f, next_step: e.target.value })} placeholder="e.g. Follow up by email" /></Field>
          <Field label="Due" htmlFor="and"><Input id="and" type="date" disabled={!canWrite} value={f.next_step_due ?? ""} onChange={(e) => setF({ ...f, next_step_due: e.target.value })} /></Field>
          <Field label="CV used" htmlFor="acv"><Select id="acv" disabled={!canWrite} value={f.cv_asset_id ?? ""} onChange={(e) => setF({ ...f, cv_asset_id: e.target.value })}>
            <option value="">None</option>{cvs.data?.map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}</Select></Field>
          <Field label="Letter or proposal used" htmlFor="alt"><Select id="alt" disabled={!canWrite} value={f.letter_asset_id ?? ""} onChange={(e) => setF({ ...f, letter_asset_id: e.target.value })}>
            <option value="">None</option>{[...(letters.data ?? []), ...(proposals.data ?? [])].map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}</Select></Field>
          <Field label="Contact" htmlFor="ac"><Input id="ac" disabled={!canWrite} value={f.contact ?? ""} onChange={(e) => setF({ ...f, contact: e.target.value })} /></Field>
          <Field label="Pay you asked for" htmlFor="ap"><Input id="ap" disabled={!canWrite} value={f.expected_pay ?? ""} onChange={(e) => setF({ ...f, expected_pay: e.target.value })} /></Field>
        </div>
        <Field label="Notes" htmlFor="an"><Textarea id="an" rows={3} disabled={!canWrite} value={f.notes ?? ""} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
        {f.status === "applied" && a.status !== "applied" && <Notice>“Applied” is your record that you applied yourself. Nothing is submitted from this app.</Notice>}
        <section><h3 className="mb-2 font-semibold">History</h3>
          <ol className="relative border-l border-line pl-4">{[...a.history].reverse().map((h, i) => (
            <li key={i} className="mb-3"><span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full bg-d3" aria-hidden />
              <div className="text-[14px] font-semibold">{LABEL[h.status] ?? h.status}</div>
              <div className="text-[13px] text-muted">{fmtDate(h.at, { day: "numeric", month: "short", year: "numeric" })}{h.note ? ` · ${h.note}` : ""}</div></li>))}</ol></section>
      </div>
    </Drawer>
  );
}

export default function Applications() {
  const { ws, base, canWrite } = useWs();
  const toast = useToast();
  const router = useRouter();
  const open = useSearchParams().get("open");
  const [tab, setTab] = useState<"active" | "closed" | "all">("active");
  const [adding, setAdding] = useState(false);
  const [nf, setNf] = useState({ title: "", organisation: "", url: "", status: "preparing" });
  const list = useApi<ApplicationRow[]>(`/v1/workspaces/${ws.id}/freelancer/applications`);
  const rows = (list.data ?? []).filter((a) => tab === "all" || (tab === "active") === ACTIVE.includes(a.status));
  const counts = Object.fromEntries(APP_STATUSES.map((s) => [s, (list.data ?? []).filter((a) => a.status === s).length]));
  const setOpen = (id: string | null) => router.replace(id ? `${base}/applications?open=${id}` : `${base}/applications`);
  const today = new Date().toISOString().slice(0, 10);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Applications" description="Track every job and proposal: status, next steps, the CV and letter you used, and what happened.">
        {canWrite && <Button icon={<Plus className="h-4 w-4" />} onClick={() => setAdding(true)}>Add application</Button>}
      </PageHeader>
      <div className="flex gap-2 overflow-x-auto pb-1" aria-label="Pipeline">
        {ACTIVE.map((s) => <div key={s} className="min-w-[120px] flex-1 rounded-m border border-line bg-raised p-3">
          <div className="text-[12px] font-semibold uppercase tracking-[0.6px] text-muted">{LABEL[s]}</div><div className="font-mono text-[24px] font-semibold">{counts[s]}</div></div>)}
      </div>
      <Tabs value={tab} onChange={setTab} items={[{ id: "active", label: "Active" }, { id: "closed", label: "Closed" }, { id: "all", label: "All" }]} />
      {!list.data && <Skeleton className="h-40" />}
      {list.data && rows.length === 0 && <EmptyState tone="d3" icon={<ClipboardList className="h-6 w-6" />} title="Nothing here yet"
        action={<Link className="font-semibold text-orange-text underline" href={`${base}/opportunities`}>Start from an opportunity</Link>}>Add an application to track it.</EmptyState>}
      <ul className="divide-y divide-line overflow-hidden rounded-m border border-line bg-raised">
        {rows.map((a) => (
          <li key={a.id}><button onClick={() => setOpen(a.id)} className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 p-4 text-left hover:bg-sunken/50">
            <span className="min-w-0 flex-1"><span className="block truncate font-semibold">{a.title}</span>
              <span className="block text-[13px] text-muted">{a.organisation || "–"}{a.applied_on ? ` · applied ${fmtDate(a.applied_on)}` : ""}</span></span>
            {a.next_step && <span className={cx("text-[13px]", a.next_step_due && a.next_step_due < today ? "font-semibold text-danger" : "text-muted")}>
              {a.next_step}{a.next_step_due ? ` · ${fmtDate(a.next_step_due)}` : ""}</span>}
            <StatusBadge status={a.status} /></button></li>))}
      </ul>
      {open && <Detail id={open} onClose={() => setOpen(null)} onChanged={list.reload} />}
      <Modal open={adding} onClose={() => setAdding(false)} title="Add an application"
        footer={<><Button variant="ghost" onClick={() => setAdding(false)}>Cancel</Button><Button disabled={!nf.title.trim() || (!!nf.url && !/^https?:\/\/\S+$/.test(nf.url))} onClick={async () => {
          try { const a = await post<ApplicationRow>(`/v1/workspaces/${ws.id}/freelancer/applications`, { ...nf, url: nf.url || null });
            toast("Added"); setAdding(false); setNf({ title: "", organisation: "", url: "", status: "preparing" }); list.reload(); setOpen(a.id); }
          catch (e) { toast(errorText(e), "danger"); }
        }}>Add</Button></>}>
        <div className="flex flex-col gap-4">
          <Field label="Role or project" htmlFor="nt"><Input id="nt" value={nf.title} onChange={(e) => setNf({ ...nf, title: e.target.value })} /></Field>
          <Field label="Company or client" htmlFor="no"><Input id="no" value={nf.organisation} onChange={(e) => setNf({ ...nf, organisation: e.target.value })} /></Field>
          <Field label="Link (optional)" htmlFor="nu"><Input id="nu" value={nf.url} placeholder="https://" onChange={(e) => setNf({ ...nf, url: e.target.value })} /></Field>
          <Field label="Status" htmlFor="ns"><Select id="ns" value={nf.status} onChange={(e) => setNf({ ...nf, status: e.target.value })}>{APP_STATUSES.map((s) => <option key={s} value={s}>{LABEL[s]}</option>)}</Select></Field>
        </div>
      </Modal>
    </div>
  );
}
