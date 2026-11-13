"use client";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { tool } from "@/lib/biz";
import { Thinking, ToolForm, ToolResult, useBizGenerate } from "@/components/biz/tools";
import { useWs } from "@/components/Shell";
import { Card, Notice, PageHeader } from "@/components/ui";

const NOTES: Record<string, string> = {
  market: "Based on your profile, notes and documents. No live market data or web research is connected, so it tells you what to check.",
  competitors: "Only the competitors you named, using what you've observed. It can't look at their accounts, prices or ads.",
  ads: "Plans only. No ad account is connected: nothing is launched or paid. You can request approval to spend as a record.",
  report: "Analyses the results you've recorded for these dates. Every number must come from your figures.",
};

export default function ToolPage() {
  const { tool: key } = useParams<{ tool: string }>();
  const { base, canWrite } = useWs();
  const def = tool(key);
  const g = useBizGenerate();
  const [params, setParams] = useState<Record<string, unknown>>({});
  if (!def) return <Notice tone="danger">That tool doesn't exist. <Link className="underline" href={`${base}/tools`}>See all tools</Link>.</Notice>;
  return (
    <div className="flex flex-col gap-6">
      <Link href={`${base}/tools`} className="inline-flex items-center gap-1 text-[14px] font-semibold text-muted hover:text-ink"><ArrowLeft className="h-4 w-4" />All tools</Link>
      <PageHeader title={def.title} description={def.blurb} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
        <Card className="h-fit">
          <ToolForm key={def.key} def={def} busy={g.busy} disabled={!canWrite} onRun={(b) => { setParams(b); g.run(b); }} />
          {NOTES[def.key] && <p className="mt-4 text-[13px] text-muted">{NOTES[def.key]}</p>}
        </Card>
        <div className="flex min-w-0 flex-col gap-4">
          {g.error && <Notice tone="danger">{g.error}</Notice>}
          {g.busy && <Thinking label="Working on it…" />}
          {g.result && <ToolResult ex={g.result} def={def} params={params} />}
          {!g.busy && !g.result && !g.error && <div className="rounded-m border border-dashed border-control/60 p-8 text-center text-muted">Your result will appear here.</div>}
        </div>
      </div>
    </div>
  );
}
