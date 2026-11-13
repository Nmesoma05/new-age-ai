"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useApi } from "@/lib/api";
import type { ClientProfile } from "@/lib/types";
import { useWs } from "@/components/Shell";
import { BrandForm, BrandResult, CalendarForm, CalendarResult, CampaignForm, CampaignResult, ContentForm, ContentResults,
  Generating, ResearchForm, TextResult, useGenerate } from "@/components/studio";
import { Card, Notice, PageHeader, Tabs } from "@/components/ui";

type Tool = "content" | "brand_voice" | "calendar" | "campaign" | "research";
const TOOLS: { id: Tool; label: string; blurb: string }[] = [
  { id: "content", label: "Content", blurb: "Posts, threads, captions and scripts in this client's voice." },
  { id: "brand_voice", label: "Brand voice", blurb: "Voice, personas and content pillars you can apply to the profile." },
  { id: "calendar", label: "Calendar plan", blurb: "A social strategy and dated calendar you can import." },
  { id: "campaign", label: "Campaign", blurb: "Phases, channels, deliverables and how to measure it." },
  { id: "research", label: "Audience & competitors", blurb: "Analysis of what you've recorded about the audience and competitors." },
];

export default function Studio() {
  const { ws, base, canWrite } = useWs();
  const router = useRouter();
  const profile = useApi<ClientProfile>(`/v1/workspaces/${ws.id}/client-account`);
  const [tool, setTool] = useState<Tool>("content");
  const g = useGenerate();
  const platforms = profile.data?.platforms ?? [];
  const props = { onRun: g.run, busy: g.busy, disabled: !canWrite };
  return (
    <div>
      <PageHeader title="Studio" eyebrow="AI tools" description="Draft, plan and strategise for this client. Nothing is posted: you review, edit and save." />
      <Tabs value={tool} onChange={(t) => { setTool(t); g.setResult(null); }} items={TOOLS.map((t) => ({ id: t.id, label: t.label }))} />
      <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(320px,420px)_1fr]">
        <Card className="h-fit">
          <p className="mb-4 text-[14px] text-muted">{TOOLS.find((t) => t.id === tool)!.blurb}</p>
          {!canWrite && <div className="mb-4"><Notice tone="warning">Your role can view this workspace but can't run the AI.</Notice></div>}
          {tool === "content" && <ContentForm {...props} platforms={platforms} />}
          {tool === "brand_voice" && <BrandForm {...props} />}
          {tool === "calendar" && <CalendarForm {...props} platforms={platforms} />}
          {tool === "campaign" && <CampaignForm {...props} platforms={platforms} />}
          {tool === "research" && <ResearchForm {...props} />}
        </Card>
        <section aria-live="polite" className="min-w-0">
          {g.error && <Notice tone="danger" title="Couldn't generate">{g.error} Your brief is still here; try again.</Notice>}
          {g.busy && <Generating label="Working on it…" />}
          {!g.busy && !g.result && !g.error && (
            <div className="grid h-full min-h-[240px] place-items-center rounded-m border border-dashed border-control/60 p-8 text-center text-muted">
              Results appear here. Every result shows what the assistant wasn't sure about.</div>
          )}
          {g.result && g.result.run.status !== "succeeded" && <TextResult ex={g.result} />}
          {g.result?.run.status === "succeeded" && (
            tool === "content" ? <ContentResults ex={g.result} />
              : tool === "brand_voice" ? <BrandResult ex={g.result} onApplied={profile.reload} />
              : tool === "calendar" ? <CalendarResult ex={g.result} onImported={() => router.push(`${base}/calendar`)} />
              : tool === "campaign" ? <CampaignResult ex={g.result} onCreated={(id) => router.push(`${base}/campaigns/${id}`)} />
              : <TextResult ex={g.result} />
          )}
        </section>
      </div>
    </div>
  );
}
