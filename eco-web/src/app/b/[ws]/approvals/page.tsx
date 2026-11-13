"use client";
import { ShieldCheck } from "lucide-react";
import { useState } from "react";
import { ApiError, errorText, post, useApi } from "@/lib/api";
import { channelLabel, type PendingAction } from "@/lib/biz";
import type { Page } from "@/lib/types";
import { useWs } from "@/components/Shell";
import { Button, Card, EmptyState, Notice, PageHeader, Skeleton, StatusBadge, Tabs, fmtDate, useToast } from "@/components/ui";

const KIND: Record<string, string> = { spend_money: "Spend money", send_message: "Send a message", publish_post: "Publish a post" };

export default function Approvals() {
  const { ws, isAdmin } = useWs();
  const toast = useToast();
  const [tab, setTab] = useState<"awaiting_approval" | "all">("awaiting_approval");
  const list = useApi<Page<PendingAction>>(`/v1/workspaces/${ws.id}/actions?limit=50${tab === "all" ? "" : "&status=awaiting_approval"}`);
  const [blocked, setBlocked] = useState<Record<string, string>>({});
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Approvals" description="Anything that would leave this app (spending money, messaging customers) needs approval first." />
      <Notice tone="warning" title="No ad account or messaging service is connected">
        Approving can't launch, pay or send anything yet. Use these as a record of what was agreed, then do it yourself and record the results.</Notice>
      <Tabs value={tab} onChange={setTab} items={[{ id: "awaiting_approval", label: "Waiting" }, { id: "all", label: "All" }]} />
      {!list.data && <Skeleton className="h-40" />}
      {list.data?.data.length === 0 && <EmptyState tone="d2" icon={<ShieldCheck className="h-6 w-6" />} title="Nothing waiting">Requests from ad plans appear here.</EmptyState>}
      <ul className="flex flex-col gap-3">
        {list.data?.data.map((a) => (
          <li key={a.id}><Card className="flex flex-col gap-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div><div className="text-[12px] font-semibold uppercase tracking-[0.6px] text-muted">{KIND[a.kind] ?? a.kind}</div>
                <div className="text-[17px] font-semibold">{a.title}</div></div>
              <StatusBadge status={a.status} />
            </div>
            <dl className="grid gap-2 text-[14px] sm:grid-cols-3">
              {a.payload.amount && <div><dt className="text-muted">Amount</dt><dd className="font-mono font-semibold">{a.payload.currency} {Number(a.payload.amount).toLocaleString("en-GB")}</dd></div>}
              {a.payload.channel && <div><dt className="text-muted">Channel</dt><dd>{channelLabel(a.payload.channel)}</dd></div>}
              <div><dt className="text-muted">Requested</dt><dd>{fmtDate(a.created_at)} · expires {fmtDate(a.expires_at)}</dd></div>
              {a.payload.notes && <div className="sm:col-span-3"><dt className="text-muted">Notes</dt><dd>{a.payload.notes}</dd></div>}
            </dl>
            {a.from_untrusted && <Notice tone="warning">This came from a run that read documents or web content. Check it carefully.</Notice>}
            {blocked[a.id] && <Notice tone="info" title="Can't carry this out yet">{blocked[a.id]}</Notice>}
            {a.status === "awaiting_approval" && (isAdmin ? (
              <div className="flex flex-wrap gap-2">
                <Button onClick={async () => {
                  try { await post(`/v1/workspaces/${ws.id}/actions/${a.id}/approve`, {}); toast("Approved"); list.reload(); }
                  catch (e) {
                    if (e instanceof ApiError && e.code === "no_executor") setBlocked({ ...blocked, [a.id]: e.detail });
                    else toast(errorText(e), "danger");
                  }
                }}>Approve</Button>
                <Button variant="secondary" onClick={async () => {
                  try { await post(`/v1/workspaces/${ws.id}/actions/${a.id}/reject`, { reason: "Not now" }); toast("Rejected"); list.reload(); } catch (e) { toast(errorText(e), "danger"); }
                }}>Reject</Button>
              </div>) : <p className="text-[13px] text-muted">A workspace admin decides. Spending also needs an organisation owner or admin.</p>)}
          </Card></li>))}
      </ul>
    </div>
  );
}
