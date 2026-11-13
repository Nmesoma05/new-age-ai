"use client";
// External data on the opportunities page: the Remotive feed and indicative currency conversion.
// Both show their source and attribution, and say plainly when the service is unavailable.
import { ExternalLink, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError, errorText, post, useApi } from "@/lib/api";
import type { Opportunity, Profile } from "@/lib/fl";
import { useWs } from "@/components/Shell";
import { Badge, Button, Field, Input, Modal, Notice, Skeleton, fmtDate, useToast } from "@/components/ui";

type Job = { id: string; url: string; title: string; company: string; category: string; job_type: string; published: string; location: string; salary: string; snippet: string };
type Feed = { jobs: Job[]; fetched_at: string; stale: boolean; attribution: { text: string; url: string; terms: string } };
type Fx = { converted: number; to: string; rates_updated: string; stale: boolean; attribution: { text: string; url: string }; note: string };

export function RemotiveFinder({ open, onClose, onImported }: { open: boolean; onClose: () => void; onImported: (id: string) => void }) {
  const { ws, canWrite } = useWs();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [saving, setSaving] = useState("");
  const feed = useApi<Feed>(open ? `/v1/workspaces/${ws.id}/jobs/remotive?q=${encodeURIComponent(term)}` : null);
  return (
    <Modal open={open} onClose={onClose} wide title="Find remote jobs on Remotive">
      <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); setTerm(q.trim()); }}>
        <div className="flex-1"><Field label="Search title, company or skills" htmlFor="rq"><Input id="rq" value={q} maxLength={100} onChange={(e) => setQ(e.target.value)} placeholder="e.g. product designer" /></Field></div>
        <Button type="submit" icon={<Search className="h-4 w-4" />}>Search</Button>
      </form>
      {feed.error && <div className="mt-4"><Notice tone="danger" title="The job feed isn't available right now">{errorText(feed.error)} You can still add roles you find yourself.</Notice></div>}
      {!feed.data && !feed.error && <Skeleton className="mt-4 h-40" />}
      {feed.data && <>
        <p className="mt-3 text-[13px] text-muted">
          <a className="font-semibold underline" href={feed.data.attribution.url} target="_blank" rel="noreferrer">{feed.data.attribution.text}</a>. {feed.data.attribution.terms}
          {" "}Feed fetched {fmtDate(feed.data.fetched_at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}{feed.data.stale ? " (couldn't refresh, showing the last copy)" : ""}.
        </p>
        {feed.data.jobs.length === 0 && <p className="mt-4 text-[14px]">No listings match. Try fewer or different words.</p>}
        <ul className="mt-3 flex max-h-[55vh] flex-col gap-2 overflow-auto">
          {feed.data.jobs.map((j) => (
            <li key={j.id} className="rounded-m border border-line p-3">
              <div className="flex flex-wrap items-start gap-2">
                <div className="min-w-0 flex-1"><div className="font-semibold">{j.title}</div>
                  <div className="text-[13px] text-muted">{j.company} · {j.category}{j.published ? ` · posted ${fmtDate(j.published)}` : ""}</div></div>
                {canWrite && <Button size="sm" loading={saving === j.id} onClick={async () => {
                  setSaving(j.id);
                  try { const r = await post<{ id: string }>(`/v1/workspaces/${ws.id}/jobs/remotive/import`, { job_id: j.id }); toast("Saved. Check it's still open before applying."); onImported(r.id); }
                  catch (e) {
                    if (e instanceof ApiError && e.code === "already_saved") onImported(String(e.extra.id));
                    else toast(errorText(e), "danger");
                  } finally { setSaving(""); }
                }}>Save</Button>}
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-[12px]">
                <Badge>{j.location ? `Location: ${j.location}` : "Location not stated"}</Badge>
                {j.salary && <Badge tone="neutral">Salary as listed: {j.salary}</Badge>}
              </div>
              <p className="mt-2 line-clamp-2 text-[13px] text-muted">{j.snippet}</p>
              <a className="mt-1 inline-flex items-center gap-1 text-[13px] font-semibold underline" href={j.url} target="_blank" rel="noopener noreferrer nofollow">View on Remotive<ExternalLink className="h-3.5 w-3.5" /></a>
            </li>))}
        </ul>
      </>}
    </Modal>
  );
}

export function useHomeCurrency(): string | null {
  const { ws } = useWs();
  const p = useApi<Profile>(`/v1/workspaces/${ws.id}/professional-profile`);
  return p.data?.currency ?? null;
}

export function FxLine({ o, to }: { o: Opportunity; to: string | null }) {
  const [fx, setFx] = useState<{ min?: Fx; max?: Fx; err?: string } | null>(null);
  const from = o.pay_currency;
  useEffect(() => {
    if (!from || !to || from === to || o.pay_min === null) return;
    const get = (a: number) => fetch(`/api/proxy/v1/fx/convert?amount=${a}&from=${from}&to=${to}`, { cache: "no-store" })
      .then(async (r) => { const b = await r.json(); if (!r.ok) throw new Error(b.detail || "unavailable"); return b as Fx; });
    Promise.all([get(o.pay_min), o.pay_max ? get(o.pay_max) : Promise.resolve(undefined)])
      .then(([min, max]) => setFx({ min, max })).catch((e) => setFx({ err: String(e.message) }));
  }, [from, to, o.pay_min, o.pay_max]);
  if (!from || !to || from === to || o.pay_min === null) return null;
  if (!fx) return <span className="block text-[12px] text-muted">Converting…</span>;
  if (fx.err || !fx.min) return <span className="block text-[12px] text-muted">Not converted: the exchange-rate service isn't available right now.</span>;
  const n = (x: number) => x.toLocaleString("en-GB", { maximumFractionDigits: 0 });
  return (
    <span className="block text-[12px] text-muted">
      ≈ {to} {n(fx.min.converted)}{fx.max ? `–${n(fx.max.converted)}` : ""} at the {fx.min.stale ? "last available" : "daily"} rate ({fx.min.rates_updated?.slice(5, 16)}).{" "}
      {fx.min.note}{" "}<a className="underline" href={fx.min.attribution.url} target="_blank" rel="noreferrer">{fx.min.attribution.text}</a>
    </span>
  );
}
