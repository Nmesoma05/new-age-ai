"use client";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { flTool } from "@/lib/fl";
import { FlToolForm, FlToolResult, Working, useFlGenerate } from "@/components/fl/tools";
import { useWs } from "@/components/Shell";
import { Card, Notice, PageHeader } from "@/components/ui";

export default function FlToolPage() {
  const { tool: key } = useParams<{ tool: string }>();
  const sp = useSearchParams();
  const { base, canWrite } = useWs();
  const def = flTool(key);
  const g = useFlGenerate();
  if (!def) return <Notice tone="danger">That tool doesn't exist. <Link className="underline" href={base}>Back to your dashboard</Link>.</Notice>;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={def.title} description={def.blurb} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,400px)_minmax(0,1fr)]">
        <Card className="h-fit">
          <FlToolForm key={def.key} def={def} busy={g.busy} disabled={!canWrite} onRun={g.run}
            initial={{ opportunity: sp.get("opportunity"), application: sp.get("application") }} />
        </Card>
        <div className="flex min-w-0 flex-col gap-4">
          {g.error && <Notice tone="danger">{g.error}</Notice>}
          {g.busy && <Working label="Working on it…" />}
          {g.result && <FlToolResult ex={g.result} def={def} />}
          {!g.busy && !g.result && !g.error && <div className="rounded-m border border-dashed border-control/60 p-8 text-center text-muted">
            Your result will appear here. It uses only your profile and what you add on the left.</div>}
        </div>
      </div>
    </div>
  );
}
