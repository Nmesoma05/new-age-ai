"use client";
import { Mic, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { errorText, post, useApi } from "@/lib/api";
import type { InterviewSession } from "@/lib/fl";
import { useWs } from "@/components/Shell";
import { Button, Card, EmptyState, Field, Input, LinkButton, Modal, PageHeader, Skeleton, StatusBadge, Textarea, fmtDate, useToast } from "@/components/ui";

export default function Interviews() {
  const { ws, base, canWrite } = useWs();
  const toast = useToast();
  const list = useApi<InterviewSession[]>(`/v1/workspaces/${ws.id}/freelancer/interviews`);
  const [open, setOpen] = useState(false);
  const [role, setRole] = useState("");
  const [qs, setQs] = useState("Tell me about yourself.\nWhy do you want to work remotely?\nTell me about a project you're proud of.");
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Interview practice" description="Answer real questions out loud or in writing, get scored feedback and a stronger version built from your own facts.">
        <LinkButton href={`${base}/tools/interview`}>Prepare for a role</LinkButton>
        {canWrite && <Button icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>Practise my own questions</Button>}
      </PageHeader>
      <Card className="flex flex-col gap-1 bg-d3-soft/60">
        <div className="font-semibold">How it works</div>
        <ol className="list-decimal pl-5 text-[14px]"><li>Get likely questions for a role (or bring your own).</li><li>Type your answer the way you'd say it.</li>
          <li>See scores for structure, relevance, specificity and clarity, plus a stronger version that uses only your facts.</li></ol>
      </Card>
      {!list.data && <Skeleton className="h-32" />}
      {list.data?.length === 0 && <EmptyState tone="d3" icon={<Mic className="h-6 w-6" />} title="No practice sessions yet"
        action={<Link className="font-semibold text-orange-text underline" href={`${base}/tools/interview`}>Prepare for a role</Link>}>Start with interview prep, then practise.</EmptyState>}
      <ul className="grid gap-3 md:grid-cols-2">{list.data?.map((s) => (
        <li key={s.id}><Link href={`${base}/interview/${s.id}`} className="flex flex-col gap-1 rounded-m border border-line bg-raised p-4 transition hover:border-control hover:shadow-1">
          <div className="flex items-start justify-between gap-2"><span className="font-semibold">{s.role_title}</span><StatusBadge status={s.status === "active" ? "in_progress" : "done"} /></div>
          <span className="text-[13px] text-muted">{s.answers.length} of {s.questions.length} answered · {fmtDate(s.created_at)}</span></Link></li>))}</ul>
      <Modal open={open} onClose={() => setOpen(false)} title="Practise your own questions"
        footer={<><Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button><Button disabled={!role.trim() || !qs.trim()} onClick={async () => {
          try {
            const s = await post<{ id: string }>(`/v1/workspaces/${ws.id}/freelancer/interviews`, { role_title: role.trim(),
              questions: qs.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 15) });
            location.href = `${base}/interview/${s.id}`;
          } catch (e) { toast(errorText(e), "danger"); }
        }}>Start</Button></>}>
        <div className="flex flex-col gap-4">
          <Field label="Role" htmlFor="ir"><Input id="ir" value={role} onChange={(e) => setRole(e.target.value)} placeholder="e.g. Customer success, remote" /></Field>
          <Field label="Questions (one per line)" htmlFor="iq"><Textarea id="iq" rows={6} value={qs} onChange={(e) => setQs(e.target.value)} /></Field>
        </div>
      </Modal>
    </div>
  );
}
