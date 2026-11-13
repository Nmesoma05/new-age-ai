"use client";
import { Bot, Paperclip, Plus, Send, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, errorText, post, useApi } from "@/lib/api";
import type { Exchange, Message, Page, RunSummary } from "@/lib/types";
import { RunPanel } from "@/components/RunPanel";
import { useWs } from "@/components/Shell";
import { Badge, Button, Markdown, Notice, Textarea, cx, fmtTime, useToast } from "@/components/ui";

type Conv = { id: string; title: string; created_at: string; updated_at: string };
export default function Assistant() {
  const { ws, canWrite, division } = useWs();
  const AGENT_LABEL = division.agentLabels;
  const toast = useToast();
  const convs = useApi<Page<Conv>>(`/v1/workspaces/${ws.id}/conversations?limit=50`);
  const chats = (convs.data?.data ?? []).filter((c) => !c.title.startsWith("Studio · "));
  const [active, setActive] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<(Message & { run?: RunSummary })[]>([]);
  const [text, setText] = useState("");
  const [docs, setDocs] = useState<{ id: string; filename: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const file = useRef<HTMLInputElement>(null);

  useEffect(() => { if (!active && chats.length) setActive(chats[0].id); }, [chats, active]);
  useEffect(() => {
    if (!active) { setMsgs([]); return; }
    api.get<Page<Message>>(`/v1/workspaces/${ws.id}/conversations/${active}/messages?limit=50`).then((p) => setMsgs([...p.data].reverse())).catch(() => setMsgs([]));
  }, [active, ws.id]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, busy]);

  async function send() {
    if (!text.trim()) return;
    setBusy(true); setErr("");
    try {
      let id = active;
      if (!id) {
        const c = await post<Conv>(`/v1/workspaces/${ws.id}/conversations`, { title: text.slice(0, 60) });
        id = c.id; setActive(id); convs.reload();
      }
      const ex = await post<Exchange>(`/v1/workspaces/${ws.id}/conversations/${id}/messages`, { content: text, document_ids: docs.map((d) => d.id) });
      setMsgs((m) => [...m, ex.user_message, { ...ex.assistant_message, run: ex.run }]);
      setText(""); setDocs([]);
    } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  }

  return (
    <div className="grid h-[calc(100vh-180px)] min-h-[520px] gap-4 lg:h-[calc(100vh-80px)] lg:grid-cols-[260px_1fr]">
      <aside className="hidden flex-col gap-2 overflow-y-auto rounded-m border border-line bg-raised p-3 lg:flex">
        <Button variant="secondary" size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => { setActive(null); setMsgs([]); }}>New chat</Button>
        {chats.map((c) => (
          <button key={c.id} onClick={() => setActive(c.id)} className={cx("truncate rounded-s px-2 py-2 text-left text-[14px]", active === c.id ? "bg-orange-soft font-semibold" : "hover:bg-sunken")}>{c.title}</button>))}
        {chats.length === 0 && <p className="px-2 text-[13px] text-muted">No chats yet.</p>}
      </aside>
      <section className="flex min-w-0 flex-col overflow-hidden rounded-m border border-line bg-raised">
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <div className="flex items-center gap-2 font-semibold"><Bot className={cx("h-5 w-5", division.accent.text)} />{division.product === "business" ? "Strategist" : "Assistant"}</div>
          <span className="hidden text-[13px] text-muted sm:inline">{division.assistant.scope}</span>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {msgs.length === 0 && !busy && (
            <div className="mx-auto mt-10 max-w-md text-center">
              <div className={cx("mx-auto mb-3 grid h-12 w-12 place-items-center rounded-full", division.accent.soft, division.accent.text)}><Bot className="h-6 w-6" /></div>
              <div className="font-semibold">{division.assistant.intro}</div>
              <div className="mt-3 flex flex-col gap-2">
                {division.assistant.suggestions.map((s) => (
                  <button key={s} onClick={() => setText(s)} className="rounded-m border border-line bg-cream px-3 py-2 text-[14px] hover:border-control">{s}</button>))}
              </div>
            </div>
          )}
          <ol className="flex flex-col gap-4">
            {msgs.map((m) => (
              <li key={m.id} className={cx("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                <div className={cx("max-w-[85%] rounded-l px-4 py-3 animate-rise", m.role === "user" ? "bg-ink text-cream" : "bg-cream")}>
                  {m.role === "assistant" && m.run && <div className="mb-1"><Badge tone={division.product === "business" ? "d2" : division.product === "freelancer" ? "d3" : "d1"}>{AGENT_LABEL[m.run.agent] ?? m.run.agent}</Badge></div>}
                  {m.role === "user" ? <p className="whitespace-pre-wrap">{m.content}</p> : <Markdown text={m.content} />}
                  {m.run && <div className="mt-2"><RunPanel run={m.run} /></div>}
                  <div className={cx("mt-1 text-[11px]", m.role === "user" ? "text-cream/60" : "text-muted")}>{fmtTime(m.created_at)}</div>
                </div>
              </li>))}
            {busy && <li className="flex"><div className="rounded-l bg-cream px-4 py-3 text-muted"><span className="animate-pulse">Thinking…</span></div></li>}
          </ol>
          <div ref={end} />
        </div>
        {err && <div className="px-4"><Notice tone="danger">{err}</Notice></div>}
        <form className="flex flex-col gap-2 border-t border-line p-3" onSubmit={(e) => { e.preventDefault(); send(); }}>
          {docs.length > 0 && <div className="flex flex-wrap gap-2">{docs.map((d) => (
            <span key={d.id} className="inline-flex items-center gap-1 rounded-full bg-sunken px-2.5 py-1 text-[12px]">{d.filename}
              <button type="button" aria-label={`Remove ${d.filename}`} onClick={() => setDocs(docs.filter((x) => x.id !== d.id))}><X className="h-3 w-3" /></button></span>))}</div>}
          <div className="flex items-end gap-2">
            <input ref={file} type="file" className="hidden" accept=".pdf,.docx,.txt" onChange={async (e) => {
              const f = e.target.files?.[0]; if (!f) return;
              const fd = new FormData(); fd.append("file", f);
              try { const d = await api.upload<{ id: string; filename: string; text_status: string }>(`/v1/workspaces/${ws.id}/documents`, fd);
                if (d.text_status !== "ready") toast("Uploaded, but its text couldn't be read", "danger"); else setDocs([...docs, d]); }
              catch (x) { toast(errorText(x), "danger"); }
              e.target.value = "";
            }} />
            <Button type="button" variant="ghost" aria-label="Attach a document" disabled={!canWrite} onClick={() => file.current?.click()}><Paperclip className="h-4 w-4" /></Button>
            <Textarea aria-label="Message" rows={1} className="min-h-[44px] flex-1 resize-none" placeholder={canWrite ? "Message the assistant" : "Your role can't run the AI"}
              value={text} disabled={!canWrite} onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
            <Button type="submit" loading={busy} disabled={!canWrite || !text.trim()} aria-label="Send"><Send className="h-4 w-4" /></Button>
          </div>
        </form>
      </section>
    </div>
  );
}
