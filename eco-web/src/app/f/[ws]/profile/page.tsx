"use client";
import { Sparkles } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { errorText, post, put, useApi } from "@/lib/api";
import { flTool, type Assessment, type Profile, type Reference, type SkillRead } from "@/lib/fl";
import type { Exchange } from "@/lib/types";
import { ExperienceSection, GoalsSection, PlaceSection, SkillsSection, StageSection, WorkSection, fromProfile, toBody, type Draft } from "@/components/fl/profile";
import { FlToolResult, Working } from "@/components/fl/tools";
import { useWs } from "@/components/Shell";
import { Badge, Button, Card, Field, Input, Notice, PageHeader, SectionTitle, Skeleton, Tabs, Textarea, fmtDate, useToast } from "@/components/ui";

const LEVEL: Record<SkillRead["evidence_level"], { label: string; tone: "success" | "neutral" | "d3" }> = {
  shown: { label: "Shown in your work", tone: "success" }, stated: { label: "Listed by you", tone: "neutral" },
  suggested: { label: "Suggestion: to learn", tone: "d3" } };

function AssessmentEditor({ a, onSave, disabled }: { a: Assessment; onSave: (a: Assessment) => Promise<void>; disabled: boolean }) {
  const [v, setV] = useState(a);
  const [strengths, setStrengths] = useState((a.strengths ?? []).join("\n"));
  const [busy, setBusy] = useState(false);
  useEffect(() => { setV(a); setStrengths((a.strengths ?? []).join("\n")); }, [a]);
  const skills = v.skills ?? [];
  return (
    <div className="flex flex-col gap-5">
      <Field label="Summary" htmlFor="as"><Textarea id="as" rows={3} disabled={disabled} value={v.summary ?? ""} onChange={(e) => setV({ ...v, summary: e.target.value })} /></Field>
      <Field label="Where you are" htmlFor="asr"><Textarea id="asr" rows={2} disabled={disabled} value={v.stage_read ?? ""} onChange={(e) => setV({ ...v, stage_read: e.target.value })} /></Field>
      <section><h3 className="mb-2 font-semibold">Skills</h3>
        <ul className="flex flex-col gap-2">{skills.map((s, i) => (
          <li key={s.skill + i} className="flex flex-wrap items-center gap-2 rounded-m border border-line bg-raised p-3">
            <span className="font-semibold">{s.skill}</span><Badge tone={LEVEL[s.evidence_level].tone}>{LEVEL[s.evidence_level].label}</Badge>
            <span className="w-full text-[14px] text-muted sm:w-auto sm:flex-1">{s.note}</span>
            {!disabled && <Button size="sm" variant="ghost" onClick={() => setV({ ...v, skills: skills.filter((_, j) => j !== i) })}>Remove</Button>}
          </li>))}</ul>
        <p className="mt-2 text-[13px] text-muted">"Shown" means your profile has evidence (a job, project or certificate). "Listed" means you named it but there's no example yet: add one to strengthen it.</p>
      </section>
      <Field label="Strengths (one per line)" htmlFor="ast"><Textarea id="ast" rows={4} disabled={disabled} value={strengths} onChange={(e) => setStrengths(e.target.value)} /></Field>
      {(v.gaps ?? []).length > 0 && <section><h3 className="mb-2 font-semibold">Gaps to close</h3>
        <ul className="flex flex-col gap-2">{v.gaps!.map((g, i) => <li key={i} className="rounded-m bg-sunken p-3 text-[14px]"><span className="font-semibold">{g.gap}.</span> {g.why_it_matters} <span className="text-muted">How: {g.how_to_close}</span></li>)}</ul></section>}
      {(v.suggested_directions ?? []).length > 0 && <section><h3 className="mb-2 font-semibold">Suggestions: where to focus</h3>
        <ul className="flex flex-col gap-2">{v.suggested_directions!.map((d, i) => <li key={i} className="rounded-m border border-dashed border-control/60 p-3 text-[14px]"><Badge tone="d3">{d.kind}</Badge> <span className="font-semibold">{d.title}</span>: {d.why}</li>)}</ul></section>}
      {(v.headline_options ?? []).length > 0 && <section><h3 className="mb-2 font-semibold">Suggested headlines</h3>
        <ul className="flex flex-col gap-2">{v.headline_options!.map((h, i) => <li key={i}><Input aria-label={`Headline option ${i + 1}`} disabled={disabled} value={h}
          onChange={(e) => setV({ ...v, headline_options: v.headline_options!.map((x, j) => j === i ? e.target.value : x) })} /></li>)}</ul></section>}
      {!disabled && <div><Button loading={busy} onClick={async () => {
        setBusy(true);
        try { await onSave({ ...v, strengths: strengths.split("\n").map((x) => x.trim()).filter(Boolean) }); } finally { setBusy(false); }
      }}>Save assessment</Button></div>}
    </div>
  );
}

export default function FlProfile() {
  const { ws, canWrite } = useWs();
  const toast = useToast();
  const sp = useSearchParams();
  const base = `/v1/workspaces/${ws.id}`;
  const prof = useApi<Profile>(`${base}/professional-profile`);
  const rd = useApi<Reference>("/v1/freelancer/reference");
  const [tab, setTab] = useState<"assessment" | "profile">(sp.get("tab") === "profile" ? "profile" : "assessment");
  const [d, setD] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [gen, setGen] = useState<{ busy: boolean; ex: Exchange | null; err: string }>({ busy: false, ex: null, err: "" });
  const auto = useRef(false);
  useEffect(() => { if (prof.data) setD(fromProfile(prof.data)); }, [prof.data]);
  async function assess() {
    setGen({ busy: true, ex: null, err: "" });
    try { setGen({ busy: false, ex: await post<Exchange>(`${base}/freelancer/generate`, { tool: "assessment" }), err: "" }); }
    catch (e) { setGen({ busy: false, ex: null, err: errorText(e) }); }
  }
  useEffect(() => {
    if (sp.get("assess") === "1" && prof.data && canWrite && !auto.current && !Object.keys(prof.data.assessment ?? {}).length) { auto.current = true; assess(); }
  }, [sp, prof.data, canWrite]); // eslint-disable-line react-hooks/exhaustive-deps

  if (prof.error) return <Notice tone="danger">{errorText(prof.error)}</Notice>;
  if (!prof.data || !d) return <Skeleton className="h-96" />;
  const p = prof.data;
  const has = Object.keys(p.assessment ?? {}).length > 0;
  const sec = { d, set: setD, rd: rd.data, disabled: !canWrite };
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Profile & skills" description="One profile powers every tool. Keep it true and current; the AI never adds to it on its own.">
        {canWrite && <Button ai loading={gen.busy} onClick={assess}>{has ? "Reassess my skills" : "Assess my skills"}</Button>}
      </PageHeader>
      {gen.err && <Notice tone="danger">{gen.err}</Notice>}
      {gen.busy && <Working label="Assessing your skills from your profile…" />}
      {gen.ex && <div className="flex flex-col gap-2"><div className="flex items-center gap-2 font-semibold"><Sparkles className="h-4 w-4 text-d3" />New assessment drafted. It replaces the current one only if you use it.</div>
        <FlToolResult ex={gen.ex} def={flTool("assessment")!} onApplied={() => { setGen({ busy: false, ex: null, err: "" }); prof.reload(); setTab("assessment"); }} /></div>}
      <Tabs value={tab} onChange={setTab} items={[{ id: "assessment", label: "Skills assessment" }, { id: "profile", label: "Profile details" }]} />
      {tab === "assessment" && <Card>
        <SectionTitle right={p.assessment_updated_at && <span className="text-[13px] text-muted">{p.assessment.edited_by_user ? "Edited" : "AI draft"} · {fmtDate(p.assessment_updated_at)}</span>}>Skills assessment</SectionTitle>
        {has ? <AssessmentEditor a={p.assessment} disabled={!canWrite} onSave={async (a) => {
          const { summary, stage_read, skills, strengths, gaps, suggested_directions, headline_options } = a;
          try { await put(`${base}/freelancer/assessment`, { summary, stage_read, skills, strengths, gaps, suggested_directions, headline_options }); toast("Assessment saved"); prof.reload(); }
          catch (e) { toast(errorText(e), "danger"); }
        }} /> : <Notice title="Not assessed yet">Click <span className="font-semibold">Assess my skills</span>. It reads your profile and separates what you can show from what you've listed.</Notice>}
      </Card>}
      {tab === "profile" && <div className="flex flex-col gap-5">
        {[["Where you are", <StageSection key="s" {...sec} />], ["Location & pay", <PlaceSection key="p" {...sec} />], ["Skills", <SkillsSection key="k" {...sec} />],
          ["Experience, education & certificates", <ExperienceSection key="e" {...sec} />], ["Services & portfolio", <WorkSection key="w" {...sec} />],
          ["Goals & links", <GoalsSection key="g" {...sec} />]].map(([t, el]) => <Card key={t as string}><SectionTitle>{t}</SectionTitle>{el}</Card>)}
        {canWrite && <div className="sticky bottom-20 z-10 flex justify-end sm:bottom-4"><Button loading={saving} onClick={async () => {
          setSaving(true);
          try { await put(`${base}/professional-profile`, toBody(d)); toast("Profile saved"); prof.reload(); }
          catch (e) { toast(errorText(e), "danger"); } finally { setSaving(false); }
        }}>Save profile</Button></div>}
      </div>}
    </div>
  );
}
