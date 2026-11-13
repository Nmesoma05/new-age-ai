"use client";
import { Download, FolderOpen } from "lucide-react";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, downloadUrl, useApi } from "@/lib/api";
import type { Asset, Page } from "@/lib/types";
import { AssetDrawer } from "@/components/AssetDrawer";
import { useWs } from "@/components/Shell";
import { Badge, Button, EmptyState, LinkButton, PageHeader, Skeleton, StatusBadge, Tabs, fmtDate } from "@/components/ui";

const TABS = [{ id: "", label: "All" }, { id: "draft", label: "Drafts" }, { id: "in_review", label: "In review" },
  { id: "approved", label: "Approved" }, { id: "posted", label: "Posted" }, { id: "archived", label: "Archived" }] as const;

function Library() {
  const { ws, base } = useWs();
  const params = useSearchParams();
  const router = useRouter();
  const [status, setStatus] = useState<string>("");
  const path = `/v1/workspaces/${ws.id}/assets?limit=50${status ? `&status=${status}` : ""}`;
  const list = useApi<Page<Asset>>(path);
  const [more, setMore] = useState<Asset[]>([]);
  const [cursor, setCursor] = useState<string | null | undefined>(undefined);
  const open = params.get("open");
  const items = [...(list.data?.data ?? []), ...more];
  const next = cursor === undefined ? list.data?.next_cursor : cursor;
  return (
    <div>
      <PageHeader title="Library" description="Everything saved for this client. Edit, version, send for approval and schedule.">
        <LinkButton download href={downloadUrl(`/v1/workspaces/${ws.id}/creator/library/export?format=csv${status ? `&status=${status}` : ""}`)}><Download className="h-4 w-4" />CSV</LinkButton>
        <LinkButton download href={downloadUrl(`/v1/workspaces/${ws.id}/creator/library/export?format=md${status ? `&status=${status}` : ""}`)}><Download className="h-4 w-4" />Markdown</LinkButton>
      </PageHeader>
      <Tabs value={status as typeof TABS[number]["id"]} onChange={(s) => { setStatus(s); setMore([]); setCursor(undefined); }} items={TABS.map((t) => ({ ...t }))} />
      <div className="mt-5">
        {list.loading && !list.data && <div className="flex flex-col gap-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}</div>}
        {list.data && items.length === 0 && <EmptyState icon={<FolderOpen className="h-6 w-6" />} title="Nothing here yet"
          action={<LinkButton href={`${base}/studio`} variant="primary">Create content</LinkButton>}>Drafts you save from Studio appear here.</EmptyState>}
        <ul className="grid gap-3 md:grid-cols-2">
          {items.map((a) => (
            <li key={a.id}>
              <button onClick={() => router.push(`${base}/library?open=${a.id}`)}
                className="flex w-full flex-col gap-2 rounded-m border border-line bg-raised p-4 text-left transition hover:-translate-y-0.5 hover:border-control hover:shadow-1">
                <div className="flex items-center justify-between gap-2"><StatusBadge status={a.status} /><span className="font-mono text-[12px] text-muted">v{a.current_version} · {fmtDate(a.updated_at)}</span></div>
                <div className="line-clamp-2 font-semibold">{a.title}</div>
                <div className="flex flex-wrap gap-1.5"><Badge>{a.type.replace("_", " ")}</Badge>{a.tags.map((t) => <Badge key={t} tone="d1">{t}</Badge>)}</div>
              </button>
            </li>))}
        </ul>
        {next && <div className="mt-4"><Button variant="secondary" onClick={async () => {
          const p = await api.get<Page<Asset>>(`${path}&cursor=${encodeURIComponent(next)}`);
          setMore([...more, ...p.data]); setCursor(p.next_cursor);
        }}>Load more</Button></div>}
      </div>
      {open && <AssetDrawer id={open} onClose={() => router.push(`${base}/library`)} onChanged={() => { setMore([]); setCursor(undefined); list.reload(); }} />}
    </div>
  );
}

export default function LibraryPage() { return <Suspense><Library /></Suspense>; }
