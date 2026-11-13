"use client";
import { ArrowLeft, ArrowRight, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { errorText, post, useApi } from "@/lib/api";
import type { InterviewSession } from "@/lib/fl";
import { Working } from "@/components/fl/tools";
import { useWs } from "@/components/Shell";
import { Badge, Button, Card, Field, Markdown, Notice, Skeleton, Textarea, cx, useToast } from "@/components/ui";

function Score({ label, v }: { label: string; v: number }) {
  return <div className="flex flex-col gap-1"><div className="flex justify-between text-[13px]"><span>{label}</span><span className="font-mono font-semibold">{v}/5</span></div>
    <div className="h-2 overflow-hidden rounded-full bg-sunken"><div className={cx("h-full rounded-full", v >= 4 ? "bg-success" : v >= 3 ? "bg-warning" : "bg-danger")} style={{ width: `${v * 20}%` }} /></div></div>;
}

export default function Practice() {
  const { id } = useParams<{ id: string }>();
  const { ws, base, canWrite } = useWs();
  const toast = useToast();
  const s = useApi<InterviewSession>(`/v1/workspaces/${ws.id}/freelancer/interviews/${id}`);
  const [i, setI] = useState(0);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const d = s.data;
  const done = d?.answers.find((a) => a.index === i);
  useEffect(() => { setAnswer(done?.answer ?? ""); }, [i, done?.answer]);
  if (s.error) return <Notice tone="danger">{errorText(s.error)}</Notice>;
  if (!d) return <Skeleton className="h-96" />;
  const q = d.questions[i];
  const fb = done?.feedback as { scores?: Record<string, number> } | null | undefined;
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-5">
      <Link href={`${base}/interview`} className="inline-flex items-center gap-1 text-[14px] font-semibold text-muted hover:text-ink"><ArrowLeft className="h-4 w-4" />All practice</Link>
      <div><div className="text-[13px] font-semibold uppercase tracking-[0.6px] text-d3">{d.role_title}</div>
        <div className="mt-2 flex gap-1" aria-label="Progress">{d.questions.map((_, k) => <button key={k} onClick={() => setI(k)} aria-label={`Question ${k + 1}`}
          className={cx("h-2 flex-1 rounded-full", k === i ? "bg-d3" : d.answers.some((a) => a.index === k) ? "bg-success" : "bg-sunken")} />)}</div></div>
      <Card className="flex flex-col gap-4">
        <div className="flex items-center gap-2"><Badge tone="d3">Question {i + 1} of {d.questions.length}</Badge>{q.type !== "own" && <Badge>{q.type.replace(/_/g, " ")}</Badge>}</div>
        <h1 className="font-display text-[24px] font-semibold leading-[30px]">{q.question}</h1>
        {q.why_asked && <p className="text-[14px] text-muted">Why they ask: {q.why_asked}</p>}
        <Field label="Your answer" htmlFor="ans" hint="Write it the way you'd say it. Aim for situation → what you did → result."><Textarea id="ans" rows={7} maxLength={4000} value={answer}
          disabled={!canWrite || d.status !== "active"} onChange={(e) => setAnswer(e.target.value)} /></Field>
        <div className="flex flex-wrap items-center gap-2">
          {canWrite && d.status === "active" && <Button ai loading={busy} disabled={answer.trim().length < 20} onClick={async () => {
            setBusy(true);
            try { await post(`/v1/workspaces/${ws.id}/freelancer/interviews/${id}/answers`, { index: i, answer }); s.reload(); }
            catch (e) { toast(errorText(e), "danger"); } finally { setBusy(false); }
          }}>{done ? "Get new feedback" : "Get feedback"}</Button>}
          <span className="text-[13px] text-muted">{answer.trim().length < 20 ? "Write at least a couple of sentences." : `${answer.trim().split(/\s+/).length} words`}</span>
        </div>
      </Card>
      {busy && <Working label="Reviewing your answer…" />}
      {done && !busy && <Card className="flex flex-col gap-4 animate-rise">
        {fb?.scores && <div className="grid gap-3 sm:grid-cols-4">{Object.entries(fb.scores).map(([k, v]) => <Score key={k} label={k[0].toUpperCase() + k.slice(1)} v={v} />)}</div>}
        <Markdown text={done.feedback_text} />
      </Card>}
      <div className="flex justify-between">
        <Button variant="ghost" disabled={i === 0} onClick={() => setI(i - 1)}><ArrowLeft className="h-4 w-4" />Previous</Button>
        {i < d.questions.length - 1 ? <Button variant="secondary" onClick={() => setI(i + 1)}>Next question<ArrowRight className="h-4 w-4" /></Button>
          : d.status === "active" && canWrite ? <Button icon={<CheckCircle2 className="h-4 w-4" />} onClick={async () => {
            try { await post(`/v1/workspaces/${ws.id}/freelancer/interviews/${id}/complete`); toast("Session finished"); s.reload(); } catch (e) { toast(errorText(e), "danger"); }
          }}>Finish session</Button> : <Badge tone="success">Finished</Badge>}
      </div>
    </div>
  );
}
