"use client";
import { Building2, User } from "lucide-react";
import { useState } from "react";
import { errorText, post, useApi } from "@/lib/api";
import type { Category, Stage } from "@/lib/biz";
import { CategoryGrid, ChannelsEditor, CompetitorsEditor, GoalsEditor, OffersEditor, emptyForm, toBody, type ProfileForm } from "@/components/biz/fields";
import { TopBar } from "@/components/TopBar";
import { Button, Field, Input, Notice, Select, Textarea, cx } from "@/components/ui";

const STEPS = ["You", "Category", "Basics", "Offer & customers", "Competitors & channels", "Goals & budget"];
type Cats = { categories: Category[]; stages: Stage[] };
type State = { businesses: unknown[] };

export default function BusinessOnboarding() {
  const cats = useApi<Cats>("/v1/business/categories");
  const state = useApi<State>("/v1/business/onboarding");
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<"solo" | "team">("solo");
  const [team, setTeam] = useState("");
  const [f, setF] = useState<ProfileForm>(emptyForm("NGN"));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k: keyof ProfileForm) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const webOk = !f.website || /^https?:\/\/\S+$/.test(f.website);
  const curOk = !f.currency || /^[A-Za-z]{3}$/.test(f.currency);
  const canNext = [mode === "solo" || !!team.trim(), !!f.category, !!f.business_name.trim() && !!f.industry.trim() && webOk, true, true,
    curOk && (f.budget_amount === "" || Number(f.budget_amount) >= 0)][step];

  async function finish() {
    setBusy(true); setErr("");
    try {
      const res = await post<{ workspace_id: string }>("/v1/business/onboarding", {
        mode, team_name: mode === "team" ? team : undefined, profile: toBody(f) });
      location.href = `/b/${res.workspace_id}/profile?build=1`;
    } catch (x) { setErr(errorText(x)); setBusy(false); }
  }
  const cat = cats.data?.categories.find((c) => c.key === f.category);

  return (
    <div className="min-h-screen">
      <TopBar />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <ol className="mb-8 grid grid-cols-6 gap-2" aria-label="Progress">
          {STEPS.map((s, i) => (
            <li key={s}><div className={cx("h-1.5 rounded-full transition", i <= step ? "bg-d2" : "bg-sunken")} />
              <div className={cx("mt-2 hidden text-[12px] font-semibold sm:block", i === step ? "text-ink" : "text-muted")}>{s}</div></li>))}
        </ol>
        <p className="mb-2 text-[13px] font-semibold uppercase tracking-[0.6px] text-d2">Step {step + 1} of {STEPS.length} · {STEPS[step]}</p>
        {state.data && state.data.businesses.length > 0 && step === 0 && (
          <div className="mb-4"><Notice>You already have a business set up. <a className="underline" href="/businesses">Go to your businesses</a> or add another below.</Notice></div>)}
        {err && <div className="mb-4"><Notice tone="danger">{err}</Notice></div>}

        {step === 0 && (
          <section className="animate-rise">
            <h1 className="font-display text-[28px] font-[650] leading-[34px]">Who's doing the marketing?</h1>
            <p className="mt-1 text-muted">This decides where the business workspace lives. You can invite a team later.</p>
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              {([["solo", User, "Just me", "Owner or founder doing the marketing yourself."],
                 ["team", Building2, "A team", "Several people, or a marketing team, working on it."]] as const).map(([m, Icon, t, d]) => (
                <button key={m} type="button" onClick={() => setMode(m)} aria-pressed={mode === m}
                  className={cx("rounded-m border-2 p-5 text-left transition", mode === m ? "border-orange bg-orange-soft" : "border-line bg-raised hover:border-control")}>
                  <Icon className="h-6 w-6" /><div className="mt-3 font-semibold">{t}</div><div className="mt-1 text-[14px] text-muted">{d}</div></button>))}
            </div>
            {mode === "team" && <div className="mt-5"><Field label="Team or company name" htmlFor="team"><Input id="team" value={team} onChange={(e) => setTeam(e.target.value)} /></Field></div>}
          </section>
        )}

        {step === 1 && (
          <section className="flex flex-col gap-5 animate-rise">
            <div><h1 className="font-display text-[28px] font-[650] leading-[34px]">What kind of business is it?</h1>
              <p className="mt-1 text-muted">This tailors the advice. A café and a software company shouldn't get the same plan.</p></div>
            {cats.data ? <CategoryGrid cats={cats.data.categories} value={f.category} onChange={(category) => setF({ ...f, category })} /> : <p className="text-muted">Loading…</p>}
            {cat && <Notice tone="info" title={`Typical focus for ${cat.label.toLowerCase()}`}>{cat.focus}</Notice>}
            <Field label="Stage" htmlFor="stage"><Select id="stage" value={f.stage} onChange={set("stage")}>
              {cats.data?.stages.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}</Select></Field>
          </section>
        )}

        {step === 2 && (
          <section className="flex flex-col gap-4 animate-rise">
            <h1 className="font-display text-[28px] font-[650] leading-[34px]">The basics</h1>
            <Field label="Business name" htmlFor="bn"><Input id="bn" value={f.business_name} onChange={set("business_name")} /></Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Industry" htmlFor="bi" hint="In your words"><Input id="bi" value={f.industry} onChange={set("industry")} placeholder="e.g. Catering" /></Field>
              <Field label="Speciality (optional)" htmlFor="bs"><Input id="bs" value={f.sub_type} onChange={set("sub_type")} placeholder="e.g. Party trays" /></Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Where you're based" htmlFor="bl"><Input id="bl" value={f.location} onChange={set("location")} placeholder="City, country" /></Field>
              <Field label="Target markets" htmlFor="bt" hint="Comma separated"><Input id="bt" value={f.target_markets} onChange={set("target_markets")} placeholder="e.g. Awka, Onitsha" /></Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Who do you sell to?" htmlFor="bm"><Select id="bm" value={f.business_model} onChange={set("business_model")}>
                <option value="b2c">Consumers (B2C)</option><option value="b2b">Businesses (B2B)</option><option value="both">Both</option></Select></Field>
              <Field label="Website (optional)" htmlFor="bw" error={webOk ? undefined : "Use a full link starting with https://"}>
                <Input id="bw" value={f.website} onChange={set("website")} placeholder="https://" /></Field>
            </div>
          </section>
        )}

        {step === 3 && (
          <section className="flex flex-col gap-5 animate-rise">
            <h1 className="font-display text-[28px] font-[650] leading-[34px]">What you sell, and to whom</h1>
            <OffersEditor value={f.offers} onChange={(offers) => setF({ ...f, offers })} />
            <Field label="Ideal customers" htmlFor="bc"><Textarea id="bc" value={f.customers} onChange={set("customers")} placeholder="Who buys, why, and when they need you" /></Field>
            <Field label="What makes you different" htmlFor="bd"><Textarea id="bd" value={f.differentiators} onChange={set("differentiators")} placeholder="Why customers pick you over others" /></Field>
          </section>
        )}

        {step === 4 && (
          <section className="flex flex-col gap-5 animate-rise">
            <h1 className="font-display text-[28px] font-[650] leading-[34px]">Competitors and channels</h1>
            <CompetitorsEditor value={f.competitors} onChange={(competitors) => setF({ ...f, competitors })} />
            <div><h2 className="mb-2 font-semibold">Marketing channels</h2><ChannelsEditor value={f.channels} onChange={(channels) => setF({ ...f, channels })} /></div>
          </section>
        )}

        {step === 5 && (
          <section className="flex flex-col gap-5 animate-rise">
            <h1 className="font-display text-[28px] font-[650] leading-[34px]">Goals and budget</h1>
            <GoalsEditor value={f.goals} onChange={(goals) => setF({ ...f, goals })} />
            <div className="grid gap-4 sm:grid-cols-[1fr_120px]">
              <Field label="Monthly marketing budget (optional)" htmlFor="ba" hint="Leave empty if you don't have one yet">
                <Input id="ba" type="number" min={0} inputMode="decimal" value={f.budget_amount} onChange={set("budget_amount")} /></Field>
              <Field label="Currency" htmlFor="bcur" error={curOk ? undefined : "3 letters, e.g. NGN"}><Input id="bcur" maxLength={3} value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value.toUpperCase() })} /></Field>
            </div>
            <Field label="Budget notes" htmlFor="bbn"><Input id="bbn" value={f.budget_notes} onChange={set("budget_notes")} placeholder="e.g. Can increase in December" /></Field>
            <Notice>Next, the AI turns all of this into your Marketing Intelligence Profile. You can edit every part of it.</Notice>
          </section>
        )}

        <div className="mt-8 flex justify-between">
          <Button variant="ghost" onClick={() => setStep(step - 1)} disabled={step === 0 || busy}>Back</Button>
          {step < STEPS.length - 1 ? <Button onClick={() => setStep(step + 1)} disabled={!canNext}>Continue</Button>
            : <Button onClick={finish} loading={busy} disabled={!canNext} ai>Create & build my profile</Button>}
        </div>
      </main>
    </div>
  );
}
