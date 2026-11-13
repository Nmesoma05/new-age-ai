"use client";
import { Building2, User } from "lucide-react";
import { useState } from "react";
import { errorText, post, useApi } from "@/lib/api";
import type { OnboardingState, Platform } from "@/lib/types";
import { Logo } from "@/components/Logo";
import { PlatformPicker } from "@/components/PlatformPicker";
import { Button, Field, Input, Notice, Textarea, cx } from "@/components/ui";

const STEPS = ["How you work", "Your first client", "Audience & goals"];

export default function Onboarding() {
  const state = useApi<OnboardingState>("/v1/creator/onboarding");
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<"solo" | "agency">("solo");
  const [agency, setAgency] = useState("");
  const [c, setC] = useState({ client_name: "", industry: "", website: "", description: "", location: "",
    platforms: ["instagram"] as Platform[], audience: "", goal: "", voice: "", avoid: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k: keyof typeof c) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setC({ ...c, [k]: e.target.value });

  async function finish() {
    setBusy(true); setErr("");
    const words = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
    try {
      const res = await post<{ workspace_id: string }>("/v1/creator/onboarding", {
        mode, agency_name: mode === "agency" ? agency : undefined,
        client: {
          client_name: c.client_name, industry: c.industry || null, website: c.website || null, platforms: c.platforms,
          business_info: { description: c.description, offers: [], location: c.location },
          audience: { summary: c.audience, personas: [], locations: c.location ? [c.location] : [] },
          goals: c.goal ? [{ goal: c.goal, metric: "" }] : [],
          brand_voice: c.voice || c.avoid ? { traits: words(c.voice), words_to_avoid: words(c.avoid) } : {},
        },
      });
      location.href = `/c/${res.workspace_id}`;
    } catch (x) { setErr(errorText(x)); setBusy(false); }
  }

  const canNext = step === 0 ? mode === "solo" || agency.trim().length > 0
    : step === 1 ? c.client_name.trim().length > 0 && c.platforms.length > 0 && (!c.website || /^https?:\/\/\S+$/.test(c.website)) : true;

  return (
    <div className="min-h-screen">
      <header className="bg-sidebar px-6 py-4"><Logo inverse division="creator" /></header>
      <main className="mx-auto max-w-2xl px-4 py-10">
        <ol className="mb-8 flex gap-2" aria-label="Progress">
          {STEPS.map((s, i) => (
            <li key={s} className="flex-1">
              <div className={cx("h-1.5 rounded-full transition", i <= step ? "bg-orange" : "bg-sunken")} />
              <div className={cx("mt-2 text-[13px] font-semibold", i === step ? "text-ink" : "text-muted")}>{s}</div>
            </li>
          ))}
        </ol>
        {state.data?.has_creator_workspace && step === 0 && (
          <div className="mb-4"><Notice>You already have clients. <a className="underline" href="/clients">Go to your clients</a> or add another below.</Notice></div>
        )}
        {err && <div className="mb-4"><Notice tone="danger">{err}</Notice></div>}

        {step === 0 && (
          <section className="animate-rise">
            <h1 className="font-display text-[28px] font-[650] leading-[34px]">How do you work?</h1>
            <p className="mt-1 text-muted">This decides where your client workspaces live. You can add a team later.</p>
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              {([["solo", User, "On my own", "Freelance creator or marketer managing your own clients."],
                 ["agency", Building2, "As an agency or team", "Several people working across many clients."]] as const).map(([m, Icon, t, d]) => (
                <button key={m} type="button" onClick={() => setMode(m)} aria-pressed={mode === m}
                  className={cx("rounded-m border-2 p-5 text-left transition", mode === m ? "border-orange bg-orange-soft" : "border-line bg-raised hover:border-control")}>
                  <Icon className="h-6 w-6" /><div className="mt-3 font-semibold">{t}</div><div className="mt-1 text-[14px] text-muted">{d}</div>
                </button>
              ))}
            </div>
            {mode === "agency" && (
              <div className="mt-5"><Field label="Agency or team name" htmlFor="agency">
                <Input id="agency" value={agency} onChange={(e) => setAgency(e.target.value)} placeholder="e.g. Brightside Social" /></Field></div>
            )}
          </section>
        )}

        {step === 1 && (
          <section className="flex flex-col gap-4 animate-rise">
            <div><h1 className="font-display text-[28px] font-[650] leading-[34px]">Add your first client</h1>
              <p className="mt-1 text-muted">Each client gets its own workspace: brand, content and reports never mix.</p></div>
            <Field label="Client or brand name" htmlFor="cn"><Input id="cn" value={c.client_name} onChange={set("client_name")} placeholder="Your client's brand" /></Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Industry" htmlFor="ind"><Input id="ind" value={c.industry} onChange={set("industry")} placeholder="e.g. Food & drink" /></Field>
              <Field label="Website" htmlFor="web" hint="Optional. Starts with https://" error={c.website && !/^https?:\/\/\S+$/.test(c.website) ? "Use a full link starting with https://" : undefined}>
                <Input id="web" value={c.website} onChange={set("website")} placeholder="https://" /></Field>
            </div>
            <Field label="What do they do?" htmlFor="desc"><Textarea id="desc" value={c.description} onChange={set("description")} placeholder="What they sell, to whom, what makes them different" /></Field>
            <Field label="Location" htmlFor="loc"><Input id="loc" value={c.location} onChange={set("location")} placeholder="e.g. Lagos" /></Field>
            <Field label="Platforms you manage for them"><PlatformPicker value={c.platforms} onChange={(p) => setC({ ...c, platforms: p })} /></Field>
          </section>
        )}

        {step === 2 && (
          <section className="flex flex-col gap-4 animate-rise">
            <div><h1 className="font-display text-[28px] font-[650] leading-[34px]">Who are they talking to?</h1>
              <p className="mt-1 text-muted">Optional, but the more you add, the better the drafts. You can refine all of this later.</p></div>
            <Field label="Audience" htmlFor="aud"><Textarea id="aud" value={c.audience} onChange={set("audience")} placeholder="Who buys from them, where they spend time online" /></Field>
            <Field label="Main goal for the next few months" htmlFor="goal"><Input id="goal" value={c.goal} onChange={set("goal")} placeholder="e.g. More weekday orders" /></Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Voice in a few words" htmlFor="voice" hint="Comma separated"><Input id="voice" value={c.voice} onChange={set("voice")} placeholder="warm, witty, clear" /></Field>
              <Field label="Words to avoid" htmlFor="avoid" hint="Comma separated"><Input id="avoid" value={c.avoid} onChange={set("avoid")} placeholder="cheap, guys" /></Field>
            </div>
          </section>
        )}

        <div className="mt-8 flex justify-between">
          <Button variant="ghost" onClick={() => setStep(step - 1)} disabled={step === 0 || busy}>Back</Button>
          {step < 2 ? <Button onClick={() => setStep(step + 1)} disabled={!canNext}>Continue</Button>
            : <Button onClick={finish} loading={busy}>Create workspace</Button>}
        </div>
      </main>
    </div>
  );
}
