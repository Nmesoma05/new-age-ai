"use client";
import { CheckCircle2, Link2 } from "lucide-react";
import { useState } from "react";
import { del, errorText, post, useApi } from "@/lib/api";
import type { Asset, Comment, Page } from "@/lib/types";
import { useWs } from "@/components/Shell";
import { Button, Card, CopyButton, EmptyState, Field, Input, LinkButton, Modal, Notice, PageHeader, SectionTitle, Select, StatusBadge, fmtDate, useToast } from "@/components/ui";

type Link = { id: string; label: string; asset_ids: string[]; allow_approve: boolean; expires_at: string; last_viewed_at: string | null };
type Q = { in_review: (Asset & { last_comment: Comment | null })[]; review_links: Link[]; can_approve: boolean };

export default function Approvals() {
  const { ws, base, canWrite } = useWs();
  const toast = useToast();
  const q = useApi<Q>(`/v1/workspaces/${ws.id}/creator/approvals`);
  const [share, setShare] = useState(false);
  const [comment, setComment] = useState<Record<string, string>>({});
  async function decide(id: string, decision: "approve" | "request_changes") {
    try {
      await post(`/v1/workspaces/${ws.id}/creator/assets/${id}/decision`, { decision, comment: comment[id] ?? "" });
      toast(decision === "approve" ? "Approved" : "Changes requested"); q.reload();
    } catch (e) { toast(errorText(e), "danger"); }
  }
  return (
    <div className="flex flex-col gap-8">
      <PageHeader title="Approvals" description="Content waiting for sign-off, from your team or the client.">
        <Button icon={<Link2 className="h-4 w-4" />} onClick={() => setShare(true)} disabled={!canWrite}>Share with client</Button>
      </PageHeader>
      <section>
        <SectionTitle>Waiting for approval</SectionTitle>
        {q.data && q.data.in_review.length === 0 && <EmptyState icon={<CheckCircle2 className="h-6 w-6" />} title="All caught up">Send drafts for approval from the library.</EmptyState>}
        <div className="flex flex-col gap-3">
          {q.data?.in_review.map((a) => (
            <Card key={a.id} className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <a href={`${base}/library?open=${a.id}`} className="font-semibold hover:underline">{a.title}</a>
                <span className="text-[13px] text-muted">{a.type} · v{a.current_version} · {fmtDate(a.updated_at)}</span>
              </div>
              {a.last_comment?.body && <p className="rounded-s bg-sunken p-2 text-[14px]"><span className="font-semibold">{a.last_comment.via === "client_link" ? a.last_comment.author_name : "Team"}:</span> {a.last_comment.body}</p>}
              {canWrite && (
                <div className="flex flex-wrap items-end gap-2">
                  <div className="min-w-[220px] flex-1"><Input aria-label={`Comment on ${a.title}`} placeholder="Comment (needed to request changes)" value={comment[a.id] ?? ""} onChange={(e) => setComment({ ...comment, [a.id]: e.target.value })} /></div>
                  {q.data!.can_approve && <Button onClick={() => decide(a.id, "approve")}>Approve</Button>}
                  <Button variant="secondary" disabled={!(comment[a.id] ?? "").trim()} onClick={() => decide(a.id, "request_changes")}>Request changes</Button>
                </div>
              )}
              {!q.data!.can_approve && <p className="text-[13px] text-muted">Only a workspace admin can approve. You can comment or request changes.</p>}
            </Card>))}
        </div>
      </section>
      <section>
        <SectionTitle>Active client review links</SectionTitle>
        {q.data?.review_links.length === 0 && <p className="text-muted">No active links. Share content so the client can approve without an account.</p>}
        <ul className="flex flex-col gap-2">
          {q.data?.review_links.map((l) => (
            <li key={l.id} className="flex flex-wrap items-center justify-between gap-2 rounded-m border border-line bg-raised p-3">
              <div><div className="font-semibold">{l.label}</div>
                <div className="text-[13px] text-muted">{l.asset_ids.length} item(s) · expires {fmtDate(l.expires_at)} · {l.last_viewed_at ? `last opened ${fmtDate(l.last_viewed_at)}` : "not opened yet"}{l.allow_approve ? "" : " · comments only"}</div></div>
              {canWrite && <Button variant="ghost" size="sm" onClick={async () => { await del(`/v1/workspaces/${ws.id}/creator/review-links/${l.id}`); toast("Link withdrawn"); q.reload(); }}>Withdraw</Button>}
            </li>))}
        </ul>
      </section>
      {share && <ShareModal onClose={() => { setShare(false); q.reload(); }} />}
    </div>
  );
}

function ShareModal({ onClose }: { onClose: () => void }) {
  const { ws } = useWs();
  const drafts = useApi<Page<Asset>>(`/v1/workspaces/${ws.id}/assets?limit=100`);
  const [picked, setPicked] = useState<string[]>([]);
  const [label, setLabel] = useState("Content for review");
  const [days, setDays] = useState(7);
  const [allow, setAllow] = useState(true);
  const [url, setUrl] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const options = (drafts.data?.data ?? []).filter((a) => ["draft", "in_review", "approved"].includes(a.status));
  return (
    <Modal open wide onClose={onClose} title="Share with your client" footer={url ? <Button onClick={onClose}>Done</Button> : <>
      <Button variant="ghost" onClick={onClose}>Cancel</Button>
      <Button loading={busy} disabled={!picked.length || !label.trim()} onClick={async () => {
        setBusy(true); setErr("");
        try {
          const r = await post<{ token: string }>(`/v1/workspaces/${ws.id}/creator/review-links`, { asset_ids: picked, label, expires_in_days: days, allow_approve: allow });
          setUrl(`${location.origin}/review/${r.token}`);
        } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
      }}>Create link</Button></>}>
      {url ? (
        <div className="flex flex-col gap-3">
          <Notice tone="success" title="Link ready">Send it to your client. Anyone with the link can see these items until it expires. It's shown only once, so copy it now.</Notice>
          <div className="break-all rounded-s bg-sunken p-3 font-mono text-[13px]">{url}</div>
          <div className="flex gap-2"><CopyButton text={url} label="Copy link" /><LinkButton href={url} download>Open</LinkButton></div>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {err && <Notice tone="danger">{err}</Notice>}
          <Field label="Name for this batch" htmlFor="sl"><Input id="sl" value={label} onChange={(e) => setLabel(e.target.value)} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Link works for" htmlFor="sdays"><Select id="sdays" value={days} onChange={(e) => setDays(+e.target.value)}>
              {[1, 3, 7, 14, 30].map((d) => <option key={d} value={d}>{d} day{d > 1 ? "s" : ""}</option>)}</Select></Field>
            <label className="mt-7 inline-flex items-center gap-2 text-[14px]"><input type="checkbox" className="h-4 w-4 accent-[rgb(var(--orange))]" checked={allow} onChange={(e) => setAllow(e.target.checked)} />Client can approve</label>
          </div>
          <fieldset><legend className="mb-2 text-[14px] font-semibold">Items to include</legend>
            {options.length === 0 && <p className="text-muted">No drafts yet.</p>}
            <ul className="max-h-64 divide-y divide-line overflow-y-auto rounded-m border border-line">
              {options.map((a) => (
                <li key={a.id}><label className="flex cursor-pointer items-center gap-3 px-3 py-2">
                  <input type="checkbox" className="h-4 w-4 accent-[rgb(var(--orange))]" checked={picked.includes(a.id)} onChange={(e) => setPicked(e.target.checked ? [...picked, a.id] : picked.filter((x) => x !== a.id))} />
                  <span className="min-w-0 flex-1 truncate">{a.title}</span><StatusBadge status={a.status} /></label></li>))}
            </ul></fieldset>
          <p className="text-[13px] text-muted">Drafts you share move to "In review".</p>
        </div>
      )}
    </Modal>
  );
}
