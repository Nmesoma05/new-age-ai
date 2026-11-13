"use client";
import { useState } from "react";
import { errorText, post, useApi } from "@/lib/api";
import type { Reference } from "@/lib/fl";
import { ExperienceSection, GoalsSection, PlaceSection, SkillsSection, StageSection, WorkSection, emptyDraft, toBody, type Draft } from "@/components/fl/profile";
import { TopBar } from "@/components/TopBar";
import { Button, Notice, Skeleton, cx } from "@/components/ui";

const STEPS = [
  { t: "Where you are", h: "Where are you in your career?", p: "This shapes every suggestion. There's no wrong answer." },
  { t: "Location & pay", h: "Where you work from", p: "We use this for time zones, currencies, eligibility and how you get paid." },
  { t: "Skills", h: "Your skills", p: "List what you can do today. You'll show evidence for it next." },
  { t: "Experience", h: "Your experience", p: "Only add what's true. Tools never add qualifications or results you didn't give." },
  { t: "Services & work", h: "What you offer and what you've made", p: "Skip anything that doesn't apply yet." },
  { t: "Goals", h: "Your goals", p: "Where you want to get to. The AI builds your skills assessment from all of this next." },
];
type State = { workspace_id: string | null; can_create: boolean; max_workspaces: number; workspaces_used: number };

export default function FreelancerOnboarding() {
  const rd = useApi<Reference>("/v1/freelancer/reference");
  const st = useApi<State>("/v1/freelancer/onboarding");
  const [step, setStep] = useState(0);
  const [d, setD] = useState<Draft>(emptyDraft());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const canNext = [!!d.career_stage, !!d.country && !!d.timezone && !!d.currency, d.skills.length > 0, true, true,
    d.links.every((l) => !l.url || /^https?:\/\/\S+$/.test(l.url))][step];

  async function finish() {
    setBusy(true); setErr("");
    try {
      const r = await post<{ workspace_id: string }>("/v1/freelancer/onboarding", { profile: toBody(d) });
      location.href = `/f/${r.workspace_id}/profile?assess=1`;
    } catch (x) { setErr(errorText(x)); setBusy(false); }
  }
  const sp = { d, set: setD, rd: rd.data };
  return (
    <div className="min-h-screen">
      <TopBar />
      <main className="mx-auto max-w-3xl px-4 py-8 sm:py-10">
        <ol className="mb-6 grid grid-cols-6 gap-1.5" aria-label="Progress">
          {STEPS.map((s, i) => <li key={s.t}><div className={cx("h-1.5 rounded-full transition", i <= step ? "bg-d3" : "bg-sunken")} />
            <div className={cx("mt-2 hidden text-[12px] font-semibold sm:block", i === step ? "text-ink" : "text-muted")}>{s.t}</div></li>)}
        </ol>
        <p className="text-[13px] font-semibold uppercase tracking-[0.6px] text-d3">Step {step + 1} of {STEPS.length}</p>
        <h1 className="mt-1 font-display text-[28px] font-[650] leading-[34px]">{STEPS[step].h}</h1>
        <p className="mb-6 mt-1 text-muted">{STEPS[step].p}</p>
        {st.data?.workspace_id && <div className="mb-4"><Notice>You're already set up. <a className="underline" href={`/f/${st.data.workspace_id}`}>Open your dashboard</a>.</Notice></div>}
        {st.data && !st.data.workspace_id && !st.data.can_create && <div className="mb-4"><Notice tone="warning" title="Your plan's workspace limit is reached">
          Your personal account uses {st.data.workspaces_used} of {st.data.max_workspaces} workspace(s). Upgrade to add Freelancer Growth.</Notice></div>}
        {err && <div className="mb-4"><Notice tone="danger">{err}</Notice></div>}
        {!rd.data ? <Skeleton className="h-64" /> : <div className="animate-rise" key={step}>
          {step === 0 && <StageSection {...sp} />}
          {step === 1 && <PlaceSection {...sp} />}
          {step === 2 && <SkillsSection {...sp} />}
          {step === 3 && <ExperienceSection {...sp} />}
          {step === 4 && <WorkSection {...sp} />}
          {step === 5 && <GoalsSection {...sp} />}
        </div>}
        <div className="sticky bottom-0 mt-8 flex justify-between border-t border-line bg-cream py-3">
          <Button variant="ghost" onClick={() => setStep(step - 1)} disabled={step === 0 || busy}>Back</Button>
          {step < STEPS.length - 1 ? <Button onClick={() => setStep(step + 1)} disabled={!canNext}>Continue</Button>
            : <Button ai onClick={finish} loading={busy} disabled={!canNext}>Save & assess my skills</Button>}
        </div>
      </main>
    </div>
  );
}
