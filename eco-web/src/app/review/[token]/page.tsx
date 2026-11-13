"use client";
// Client review page: no account needed. Shows only the items in the link; the link expires.
import { CheckCircle2, MessageSquare } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, errorText, post } from "@/lib/api";
import { platformLabel } from "@/lib/types";
import { Logo } from "@/components/Logo";
import { Button, Card, Field, Input, Notice, Skeleton, StatusBadge, Textarea, fmtDate } from "@/components/ui";

type Item = { id: string; title: string; type: string; status: string; version: number; text: string; platform: string | null;
  feedback: { kind: string; name: string; body: string; version: number; at: string }[] };
type Review = { label: string; client: string; expires_at: string; allow_approve: boolean; items: Item[] };

export default function ReviewPage() {
  const { token } = useParams<{ token: string }>();
  const [data, setData] = useState<Review | null>(null);
  const [err, setErr] = useState("");
  const [name, setName] = useState("");
  useEffect(() => {
    try { setName(localStorage.getItem("eco_reviewer") ?? ""); } catch { /* storage unavailable */ }
    api.get<Review>(`/v1/review/${encodeURIComponent(token)}`).then(setData).catch((e) => setErr(errorText(e)));
  }, [token]);
  async function decide(id: string, decision: string, comment: string) {
    try {
      try { localStorage.setItem("eco_reviewer", name); } catch { /* ignore */ }
      const r = await post<{ items: Item[] }>(`/v1/review/${encodeURIComponent(token)}/assets/${id}`, { decision, name, comment });
      setData((d) => d && { ...d, items: r.items });
    } catch (e) { setErr(errorText(e)); }
  }
  return (
    <div className="min-h-screen">
      <header className="bg-sidebar px-6 py-4"><Logo inverse division="creator" /></header>
      <main className="mx-auto max-w-3xl px-4 py-8">
        {err && <Notice tone="danger">{err}</Notice>}
        {!data && !err && <Skeleton className="h-48" />}
        {data && (
          <div className="flex flex-col gap-6">
            <div>
              <div className="text-[12px] font-semibold uppercase tracking-[0.6px] text-muted">For review · {data.client}</div>
              <h1 className="mt-1 font-display text-[28px] font-[650] leading-[34px]">{data.label}</h1>
              <p className="mt-1 text-muted">{data.items.length} item(s). This link works until {fmtDate(data.expires_at, { day: "numeric", month: "long" })}.</p>
            </div>
            <Field label="Your name" htmlFor="rn" hint="Shown to the team with your feedback."><Input id="rn" value={name} onChange={(e) => setName(e.target.value)} /></Field>
            {data.items.map((it) => <ItemCard key={it.id} it={it} allowApprove={data.allow_approve} name={name} onDecide={decide} />)}
          </div>
        )}
      </main>
    </div>
  );
}

function ItemCard({ it, allowApprove, name, onDecide }: { it: Item; allowApprove: boolean; name: string;
  onDecide: (id: string, d: string, c: string) => Promise<void> }) {
  const [c, setC] = useState("");
  const [busy, setBusy] = useState("");
  const go = async (d: string) => { setBusy(d); await onDecide(it.id, d, c); setC(""); setBusy(""); };
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-[16px] font-semibold">{it.title}</h2>
        <div className="flex items-center gap-2">{it.platform && <span className="text-[13px] text-muted">{platformLabel(it.platform)}</span>}<StatusBadge status={it.status} /></div></div>
      <pre className="whitespace-pre-wrap rounded-m bg-cream p-3 font-sans text-[15px]">{it.text}</pre>
      {it.feedback.length > 0 && <ul className="flex flex-col gap-1 text-[14px]">{it.feedback.map((f, i) => (
        <li key={i} className="flex gap-2">{f.kind === "approved" ? <CheckCircle2 className="h-4 w-4 text-success" /> : <MessageSquare className="h-4 w-4 text-muted" />}
          <span><span className="font-semibold">{f.name}</span> {f.kind.replace("_", " ")}{f.body ? `: ${f.body}` : ""}</span></li>))}</ul>}
      <Textarea aria-label={`Feedback on ${it.title}`} rows={2} value={c} onChange={(e) => setC(e.target.value)} placeholder="Feedback (needed to ask for changes)" />
      <div className="flex flex-wrap gap-2">
        {allowApprove && <Button disabled={!name.trim() || it.status === "approved"} loading={busy === "approve"} onClick={() => go("approve")}>{it.status === "approved" ? "Approved" : "Approve"}</Button>}
        <Button variant="secondary" disabled={!name.trim() || !c.trim()} loading={busy === "request_changes"} onClick={() => go("request_changes")}>Ask for changes</Button>
        <Button variant="ghost" disabled={!name.trim() || !c.trim()} loading={busy === "comment"} onClick={() => go("comment")}>Comment only</Button>
      </div>
    </Card>
  );
}
