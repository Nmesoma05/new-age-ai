"use client";
// The professional profile editor, split into sections. Used by onboarding (one section per step) and the
// profile page (all sections). Empty rows are dropped on save, so half-filled entries never fail validation.
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { post } from "@/lib/api";
import { PAYMENT_OPTIONS, STAGE_ICON, type Certification, type Education, type Experience, type PortfolioItem,
  type Profile, type Reference, type Service, type Skill } from "@/lib/fl";
import { Button, Field, Input, Notice, Select, Textarea, Toggle, cx } from "../ui";

export type Draft = {
  full_name: string; headline: string; summary: string; career_stage: string; work_modes: string[];
  country: string; city: string; timezone: string; currency: string; payment_methods: string[]; languages: { language: string; level: string }[];
  skills: Skill[]; interests: string; experiences: (Experience & { achievements_text?: string })[]; education: Education[];
  certifications: Certification[]; services: Service[]; portfolio: PortfolioItem[];
  roles: string; markets: string; income_goal: string; goal_currency: string; hours_per_week: string;
  rate_hourly: string; rate_currency: string; links: { label: string; url: string }[];
};

export const emptyDraft = (): Draft => ({ full_name: "", headline: "", summary: "", career_stage: "beginner", work_modes: ["freelance"],
  country: "", city: "", timezone: typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().timeZone : "", currency: "",
  payment_methods: [], languages: [{ language: "English", level: "professional" }], skills: [], interests: "",
  experiences: [], education: [], certifications: [], services: [], portfolio: [], roles: "", markets: "", income_goal: "",
  goal_currency: "USD", hours_per_week: "", rate_hourly: "", rate_currency: "", links: [] });

const list = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const numOrNull = (s: string) => (s.trim() === "" ? undefined : Number(s));

export function toBody(d: Draft) {
  const opt = (s: string) => s.trim() || null;
  return {
    full_name: opt(d.full_name), headline: opt(d.headline), summary: opt(d.summary), career_stage: d.career_stage,
    work_modes: d.work_modes, country: opt(d.country), city: opt(d.city), timezone: opt(d.timezone), currency: opt(d.currency),
    payment_methods: d.payment_methods, languages: d.languages.filter((l) => l.language.trim()),
    skills: d.skills.filter((s) => s.name.trim()).map((s) => ({ name: s.name.trim(), ...(s.level ? { level: s.level } : {}) })),
    interests: list(d.interests),
    experiences: d.experiences.filter((e) => e.title.trim()).map(({ achievements_text, ...e }) => ({
      ...e, achievements: (achievements_text ?? (e.achievements ?? []).join("\n")).split("\n").map((x) => x.trim()).filter(Boolean) })),
    education: d.education.filter((e) => e.qualification.trim()),
    certifications: d.certifications.filter((c) => c.name.trim()).map((c) => ({ ...c, url: c.url || null })),
    services: d.services.filter((s) => s.name.trim()).map((s) => ({ ...s, price: s.price ?? null, currency: s.currency || "" })),
    portfolio: d.portfolio.filter((p) => p.title.trim()).map((p) => ({ ...p, url: p.url || null })),
    links: d.links.filter((l) => l.label.trim() && l.url.trim()),
    availability: d.hours_per_week ? { hours_per_week: Number(d.hours_per_week) } : {},
    rates: d.rate_hourly ? { hourly: Number(d.rate_hourly), currency: d.rate_currency || d.currency || "" } : {},
    targets: { roles: list(d.roles), markets: list(d.markets), ...(d.income_goal ? { income_goal_monthly: numOrNull(d.income_goal) } : {}),
      currency: d.income_goal ? d.goal_currency : "" },
  };
}

export function fromProfile(p: Profile): Draft {
  return { ...emptyDraft(), full_name: p.full_name ?? "", headline: p.headline ?? "", summary: p.summary ?? "", career_stage: p.career_stage,
    work_modes: p.work_modes, country: p.country ?? "", city: p.city ?? "", timezone: p.timezone ?? "", currency: p.currency ?? "",
    payment_methods: p.payment_methods, languages: p.languages.map((l) => ({ language: l.language, level: l.level ?? "professional" })),
    skills: p.skills, interests: p.interests.join(", "),
    experiences: p.experiences.map((e) => ({ ...e, achievements_text: (e.achievements ?? []).join("\n") })),
    education: p.education, certifications: p.certifications, services: p.services, portfolio: p.portfolio, links: p.links,
    roles: (p.targets.roles ?? []).join(", "), markets: (p.targets.markets ?? []).join(", "),
    income_goal: p.targets.income_goal_monthly ? String(p.targets.income_goal_monthly) : "", goal_currency: p.targets.currency || "USD",
    hours_per_week: p.availability.hours_per_week ? String(p.availability.hours_per_week) : "",
    rate_hourly: p.rates.hourly ? String(p.rates.hourly) : "", rate_currency: p.rates.currency ?? "" };
}

type SP = { d: Draft; set: (d: Draft) => void; rd?: Reference; disabled?: boolean };

function Rm({ onClick, label }: { onClick: () => void; label: string }) {
  return <button type="button" aria-label={label} onClick={onClick}
    className="grid h-11 w-11 shrink-0 place-items-center self-end rounded-m text-muted hover:bg-sunken hover:text-danger"><Trash2 className="h-4 w-4" /></button>;
}
const Add = ({ onClick, children }: { onClick: () => void; children: React.ReactNode }) =>
  <div><Button type="button" variant="secondary" size="sm" icon={<Plus className="h-4 w-4" />} onClick={onClick}>{children}</Button></div>;

export function StageSection({ d, set, rd, disabled }: SP) {
  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Career stage">
        {rd?.stages.map((s) => (
          <button key={s.key} type="button" role="radio" aria-checked={d.career_stage === s.key} disabled={disabled}
            onClick={() => set({ ...d, career_stage: s.key })}
            className={cx("rounded-m border-2 p-4 text-left transition", d.career_stage === s.key ? "border-orange bg-orange-soft" : "border-line bg-raised hover:border-control")}>
            <div className="text-[22px]" aria-hidden>{STAGE_ICON[s.key]}</div>
            <div className="mt-1 font-semibold">{s.label}</div><div className="mt-0.5 text-[13px] text-muted">{s.guidance}</div>
          </button>))}
      </div>
      <Field label="What are you looking for?">
        <div className="flex flex-wrap gap-2">{rd?.work_modes.map((m) => <Toggle key={m.key} disabled={disabled} on={d.work_modes.includes(m.key)}
          onChange={(on) => set({ ...d, work_modes: on ? [...d.work_modes, m.key] : d.work_modes.filter((x) => x !== m.key) })}>{m.label}</Toggle>)}</div>
      </Field>
    </div>
  );
}

export function PlaceSection({ d, set, rd, disabled }: SP) {
  const zones = Array.from(new Set([d.timezone, ...(rd?.countries.map((c) => c.timezone) ?? [])].filter(Boolean))).sort();
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Country" htmlFor="fc"><Select id="fc" disabled={disabled} value={d.country} onChange={(e) => {
          const c = rd?.countries.find((x) => x.code === e.target.value);
          set({ ...d, country: e.target.value, currency: c && !d.currency ? c.currency : d.currency || c?.currency || "",
            timezone: c && (!d.timezone || d.timezone === "UTC") ? c.timezone : d.timezone });
        }}><option value="">Choose…</option>{rd?.countries.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</Select></Field>
        <Field label="City (optional)" htmlFor="fci"><Input id="fci" disabled={disabled} value={d.city} onChange={(e) => set({ ...d, city: e.target.value })} /></Field>
        <Field label="Time zone" htmlFor="ftz" hint="Used to check overlap with clients and employers"><Select id="ftz" disabled={disabled} value={d.timezone} onChange={(e) => set({ ...d, timezone: e.target.value })}>
          <option value="">Choose…</option>{zones.map((z) => <option key={z} value={z}>{z.replace(/_/g, " ")}</option>)}</Select></Field>
        <Field label="Your currency" htmlFor="fcu"><Select id="fcu" disabled={disabled} value={d.currency} onChange={(e) => set({ ...d, currency: e.target.value })}>
          <option value="">Choose…</option>{rd?.currencies.map((c) => <option key={c} value={c}>{c}</option>)}</Select></Field>
      </div>
      <Field label="How can you receive payment?" hint="Only what works for you today; tools won't assume others">
        <div className="flex flex-wrap gap-2">{PAYMENT_OPTIONS.map((m) => <Toggle key={m} disabled={disabled} on={d.payment_methods.includes(m)}
          onChange={(on) => set({ ...d, payment_methods: on ? [...d.payment_methods, m] : d.payment_methods.filter((x) => x !== m) })}>{m}</Toggle>)}</div>
      </Field>
      <div className="flex flex-col gap-2"><span className="text-[14px] font-semibold">Languages</span>
        {d.languages.map((l, i) => (
          <div key={i} className="flex gap-2">
            <div className="min-w-0 flex-1"><Field label={`Language ${i + 1}`} htmlFor={`fl-${i}`}><Input id={`fl-${i}`} disabled={disabled} value={l.language}
              onChange={(e) => set({ ...d, languages: d.languages.map((x, j) => j === i ? { ...x, language: e.target.value } : x) })} /></Field></div>
            <div className="w-40"><Field label="Level" htmlFor={`fll-${i}`}><Select id={`fll-${i}`} disabled={disabled} value={l.level}
              onChange={(e) => set({ ...d, languages: d.languages.map((x, j) => j === i ? { ...x, level: e.target.value } : x) })}>
              {["basic", "conversational", "professional", "fluent", "native"].map((x) => <option key={x} value={x}>{x}</option>)}</Select></Field></div>
            {!disabled && <Rm label={`Remove language ${i + 1}`} onClick={() => set({ ...d, languages: d.languages.filter((_, j) => j !== i) })} />}
          </div>))}
        {!disabled && <Add onClick={() => set({ ...d, languages: [...d.languages, { language: "", level: "professional" }] })}>Add language</Add>}
      </div>
    </div>
  );
}

export function SkillsSection({ d, set, disabled }: SP) {
  const [name, setName] = useState("");
  const add = () => { if (name.trim() && !d.skills.some((s) => s.name.toLowerCase() === name.trim().toLowerCase())) set({ ...d, skills: [...d.skills, { name: name.trim(), level: "intermediate" }] }); setName(""); };
  return (
    <div className="flex flex-col gap-4">
      {!disabled && <div className="flex items-end gap-2"><div className="min-w-0 flex-1"><Field label="Add a skill" htmlFor="fsk">
        <Input id="fsk" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Figma, Python, Copywriting"
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} /></Field></div>
        <Button type="button" variant="secondary" onClick={add}>Add</Button></div>}
      <ul className="flex flex-col gap-2">{d.skills.map((s, i) => (
        <li key={s.name + i} className="flex items-center gap-2 rounded-m border border-line bg-raised px-3 py-1.5">
          <span className="min-w-0 flex-1 truncate font-semibold">{s.name}</span>
          <Select aria-label={`${s.name} level`} disabled={disabled} className="w-auto min-w-[140px]" value={s.level ?? ""}
            onChange={(e) => set({ ...d, skills: d.skills.map((x, j) => j === i ? { ...x, level: e.target.value || null } : x) })}>
            <option value="">Level?</option>{["learning", "beginner", "intermediate", "advanced", "expert"].map((x) => <option key={x} value={x}>{x}</option>)}</Select>
          {!disabled && <Rm label={`Remove ${s.name}`} onClick={() => set({ ...d, skills: d.skills.filter((_, j) => j !== i) })} />}
        </li>))}</ul>
      {d.skills.length === 0 && <p className="text-[14px] text-muted">Add the skills you actually use. You'll show evidence for them in the next steps.</p>}
      <Field label="Interests (comma separated)" htmlFor="fin"><Input id="fin" disabled={disabled} value={d.interests} onChange={(e) => set({ ...d, interests: e.target.value })} placeholder="e.g. fintech, education, climate" /></Field>
    </div>
  );
}

export function ExperienceSection({ d, set, disabled }: SP) {
  const upd = <K extends "experiences" | "education" | "certifications">(k: K, i: number, v: Partial<Draft[K][number]>) =>
    set({ ...d, [k]: (d[k] as unknown[]).map((x, j) => (j === i ? { ...(x as object), ...v } : x)) });
  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-3"><h3 className="font-semibold">Experience</h3>
        <p className="-mt-2 text-[13px] text-muted">Jobs, internships, freelance gigs, volunteering or personal projects all count. Only add what's true.</p>
        {d.experiences.map((e, i) => (
          <div key={i} className="grid gap-2 rounded-m border border-line p-3 sm:grid-cols-2">
            <Field label="Role" htmlFor={`ex-${i}`}><Input id={`ex-${i}`} disabled={disabled} value={e.title} onChange={(x) => upd("experiences", i, { title: x.target.value })} /></Field>
            <Field label="Organisation or client" htmlFor={`exo-${i}`}><Input id={`exo-${i}`} disabled={disabled} value={e.organisation ?? ""} onChange={(x) => upd("experiences", i, { organisation: x.target.value })} /></Field>
            <Field label="Type" htmlFor={`ext-${i}`}><Select id={`ext-${i}`} disabled={disabled} value={e.employment_type ?? "other"} onChange={(x) => upd("experiences", i, { employment_type: x.target.value })}>
              {["freelance", "full_time", "part_time", "contract", "internship", "volunteer", "project", "other"].map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</Select></Field>
            <Field label="When" htmlFor={`exp-${i}`}><Input id={`exp-${i}`} disabled={disabled} value={e.period ?? ""} placeholder="e.g. Jan 2025 - present" onChange={(x) => upd("experiences", i, { period: x.target.value })} /></Field>
            <div className="sm:col-span-2"><Field label="What you did and achieved (one per line)" htmlFor={`exa-${i}`} hint="Add numbers only if you can back them up">
              <Textarea id={`exa-${i}`} rows={3} disabled={disabled} value={e.achievements_text ?? (e.achievements ?? []).join("\n")} onChange={(x) => upd("experiences", i, { achievements_text: x.target.value })} /></Field></div>
            {!disabled && <div className="sm:col-span-2 flex justify-end"><Button type="button" variant="ghost" size="sm" onClick={() => set({ ...d, experiences: d.experiences.filter((_, j) => j !== i) })}>Remove</Button></div>}
          </div>))}
        {!disabled && <Add onClick={() => set({ ...d, experiences: [...d.experiences, { title: "", organisation: "", employment_type: "freelance", period: "", achievements_text: "" }] })}>Add experience</Add>}
      </section>
      <section className="flex flex-col gap-3"><h3 className="font-semibold">Education</h3>
        {d.education.map((e, i) => (
          <div key={i} className="flex flex-wrap gap-2 sm:flex-nowrap">
            <div className="min-w-0 flex-[2]"><Field label="Qualification" htmlFor={`ed-${i}`}><Input id={`ed-${i}`} disabled={disabled} value={e.qualification} onChange={(x) => upd("education", i, { qualification: x.target.value })} /></Field></div>
            <div className="min-w-0 flex-[2]"><Field label="Institution" htmlFor={`edi-${i}`}><Input id={`edi-${i}`} disabled={disabled} value={e.institution ?? ""} onChange={(x) => upd("education", i, { institution: x.target.value })} /></Field></div>
            <div className="min-w-0 flex-1"><Field label="Years" htmlFor={`edp-${i}`}><Input id={`edp-${i}`} disabled={disabled} value={e.period ?? ""} onChange={(x) => upd("education", i, { period: x.target.value })} /></Field></div>
            {!disabled && <Rm label={`Remove education ${i + 1}`} onClick={() => set({ ...d, education: d.education.filter((_, j) => j !== i) })} />}
          </div>))}
        {!disabled && <Add onClick={() => set({ ...d, education: [...d.education, { qualification: "", institution: "", period: "" }] })}>Add education</Add>}
      </section>
      <section className="flex flex-col gap-3"><h3 className="font-semibold">Certifications</h3>
        {d.certifications.map((c, i) => (
          <div key={i} className="flex flex-wrap gap-2 sm:flex-nowrap">
            <div className="min-w-0 flex-[2]"><Field label="Certificate" htmlFor={`ce-${i}`}><Input id={`ce-${i}`} disabled={disabled} value={c.name} onChange={(x) => upd("certifications", i, { name: x.target.value })} /></Field></div>
            <div className="min-w-0 flex-[2]"><Field label="Issuer" htmlFor={`cei-${i}`}><Input id={`cei-${i}`} disabled={disabled} value={c.issuer ?? ""} onChange={(x) => upd("certifications", i, { issuer: x.target.value })} /></Field></div>
            <div className="min-w-0 flex-1"><Field label="Year" htmlFor={`cey-${i}`}><Input id={`cey-${i}`} disabled={disabled} value={c.year ?? ""} onChange={(x) => upd("certifications", i, { year: x.target.value })} /></Field></div>
            {!disabled && <Rm label={`Remove certificate ${i + 1}`} onClick={() => set({ ...d, certifications: d.certifications.filter((_, j) => j !== i) })} />}
          </div>))}
        {!disabled && <Add onClick={() => set({ ...d, certifications: [...d.certifications, { name: "", issuer: "", year: "" }] })}>Add certificate</Add>}
      </section>
    </div>
  );
}

export function WorkSection({ d, set, rd, disabled }: SP) {
  const updS = (i: number, v: Partial<Service>) => set({ ...d, services: d.services.map((x, j) => (j === i ? { ...x, ...v } : x)) });
  const updP = (i: number, v: Partial<PortfolioItem>) => set({ ...d, portfolio: d.portfolio.map((x, j) => (j === i ? { ...x, ...v } : x)) });
  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-3"><h3 className="font-semibold">Services you offer (optional)</h3>
        {d.services.map((s, i) => (
          <div key={i} className="grid gap-2 rounded-m border border-line p-3 sm:grid-cols-[2fr_1fr_110px_auto]">
            <Field label="Service" htmlFor={`sv-${i}`}><Input id={`sv-${i}`} disabled={disabled} value={s.name} onChange={(x) => updS(i, { name: x.target.value })} placeholder="e.g. Landing page design" /></Field>
            <Field label="Your price (optional)" htmlFor={`svp-${i}`}><Input id={`svp-${i}`} disabled={disabled} type="number" min={0} value={s.price ?? ""} onChange={(x) => updS(i, { price: x.target.value === "" ? null : Number(x.target.value) })} /></Field>
            <Field label="Currency" htmlFor={`svc-${i}`}><Select id={`svc-${i}`} disabled={disabled} value={s.currency ?? ""} onChange={(x) => updS(i, { currency: x.target.value })}>
              <option value="">–</option>{rd?.currencies.map((c) => <option key={c} value={c}>{c}</option>)}</Select></Field>
            {!disabled && <Rm label={`Remove service ${i + 1}`} onClick={() => set({ ...d, services: d.services.filter((_, j) => j !== i) })} />}
          </div>))}
        {!disabled && <Add onClick={() => set({ ...d, services: [...d.services, { name: "", price: null, currency: d.currency }] })}>Add service</Add>}
      </section>
      <section className="flex flex-col gap-3"><h3 className="font-semibold">Portfolio</h3>
        <p className="-mt-2 text-[13px] text-muted">Client work, practice projects or things you built for yourself. Say which they are.</p>
        {d.portfolio.map((p, i) => (
          <div key={i} className="grid gap-2 rounded-m border border-line p-3 sm:grid-cols-2">
            <Field label="Project" htmlFor={`pf-${i}`}><Input id={`pf-${i}`} disabled={disabled} value={p.title} onChange={(x) => updP(i, { title: x.target.value })} /></Field>
            <Field label="Link (optional)" htmlFor={`pfu-${i}`}><Input id={`pfu-${i}`} disabled={disabled} value={p.url ?? ""} placeholder="https://" onChange={(x) => updP(i, { url: x.target.value })} /></Field>
            <Field label="Your role" htmlFor={`pfr-${i}`}><Input id={`pfr-${i}`} disabled={disabled} value={p.role ?? ""} onChange={(x) => updP(i, { role: x.target.value })} /></Field>
            <Field label="Result (only if real)" htmlFor={`pfo-${i}`}><Input id={`pfo-${i}`} disabled={disabled} value={p.outcome ?? ""} onChange={(x) => updP(i, { outcome: x.target.value })} /></Field>
            {!disabled && <div className="flex justify-end sm:col-span-2"><Button type="button" variant="ghost" size="sm" onClick={() => set({ ...d, portfolio: d.portfolio.filter((_, j) => j !== i) })}>Remove</Button></div>}
          </div>))}
        {!disabled && <Add onClick={() => set({ ...d, portfolio: [...d.portfolio, { title: "", url: "", role: "", outcome: "" }] })}>Add project</Add>}
      </section>
    </div>
  );
}

export function GoalsSection({ d, set, rd, disabled }: SP) {
  const [floor, setFloor] = useState<{ hourly_floor: number; daily_floor: number } | null>(null);
  useEffect(() => {
    const g = Number(d.income_goal), h = Number(d.hours_per_week);
    if (!(g > 0 && h > 0)) { setFloor(null); return; }
    const t = setTimeout(() => { post<{ hourly_floor: number; daily_floor: number }>("/v1/freelancer/rate-floor", { income_goal_monthly: g, hours_per_week: h }).then(setFloor).catch(() => setFloor(null)); }, 300);
    return () => clearTimeout(t);
  }, [d.income_goal, d.hours_per_week]);
  const urlOk = d.links.every((l) => !l.url || /^https?:\/\/\S+$/.test(l.url));
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Your name" htmlFor="fn"><Input id="fn" disabled={disabled} value={d.full_name} onChange={(e) => set({ ...d, full_name: e.target.value })} /></Field>
        <Field label="Headline" htmlFor="fh" hint="e.g. UI/UX designer for fintech apps"><Input id="fh" disabled={disabled} value={d.headline} maxLength={200} onChange={(e) => set({ ...d, headline: e.target.value })} /></Field>
      </div>
      <Field label="About you (optional)" htmlFor="fsu"><Textarea id="fsu" rows={3} disabled={disabled} value={d.summary} onChange={(e) => set({ ...d, summary: e.target.value })} /></Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Roles or work you want" htmlFor="fro" hint="Comma separated"><Input id="fro" disabled={disabled} value={d.roles} onChange={(e) => set({ ...d, roles: e.target.value })} placeholder="e.g. Product designer, UX audits" /></Field>
        <Field label="Where you want clients or employers" htmlFor="fma" hint="Countries or regions"><Input id="fma" disabled={disabled} value={d.markets} onChange={(e) => set({ ...d, markets: e.target.value })} placeholder="e.g. UK, US, Africa" /></Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-[1fr_110px_1fr]">
        <Field label="Monthly income goal (optional)" htmlFor="fig"><Input id="fig" type="number" min={0} disabled={disabled} value={d.income_goal} onChange={(e) => set({ ...d, income_goal: e.target.value })} /></Field>
        <Field label="Currency" htmlFor="fgc"><Select id="fgc" disabled={disabled} value={d.goal_currency} onChange={(e) => set({ ...d, goal_currency: e.target.value })}>
          {rd?.currencies.map((c) => <option key={c} value={c}>{c}</option>)}</Select></Field>
        <Field label="Hours you can work a week" htmlFor="fhw"><Input id="fhw" type="number" min={1} max={80} disabled={disabled} value={d.hours_per_week} onChange={(e) => set({ ...d, hours_per_week: e.target.value })} /></Field>
      </div>
      {floor && <Notice tone="info" title="Your minimum rate">To reach {d.goal_currency} {Number(d.income_goal).toLocaleString("en-GB")} a month at {d.hours_per_week} hours a week (assuming about 60% of hours are billable),
        charge at least <span className="font-mono font-semibold">{d.goal_currency} {floor.hourly_floor}</span> an hour, or {d.goal_currency} {floor.daily_floor} a day. That's a floor from your numbers, not a market rate.</Notice>}
      <div className="grid gap-4 sm:grid-cols-[1fr_110px]">
        <Field label="Your current hourly rate (optional)" htmlFor="frh"><Input id="frh" type="number" min={0} disabled={disabled} value={d.rate_hourly} onChange={(e) => set({ ...d, rate_hourly: e.target.value })} /></Field>
        <Field label="Currency" htmlFor="frc"><Select id="frc" disabled={disabled} value={d.rate_currency} onChange={(e) => set({ ...d, rate_currency: e.target.value })}>
          <option value="">–</option>{rd?.currencies.map((c) => <option key={c} value={c}>{c}</option>)}</Select></Field>
      </div>
      <div className="flex flex-col gap-2"><span className="text-[14px] font-semibold">Links (LinkedIn, portfolio, GitHub…)</span>
        {d.links.map((l, i) => (
          <div key={i} className="flex gap-2">
            <div className="w-36"><Field label="Label" htmlFor={`lk-${i}`}><Input id={`lk-${i}`} disabled={disabled} value={l.label} onChange={(e) => set({ ...d, links: d.links.map((x, j) => j === i ? { ...x, label: e.target.value } : x) })} /></Field></div>
            <div className="min-w-0 flex-1"><Field label="URL" htmlFor={`lku-${i}`}><Input id={`lku-${i}`} disabled={disabled} value={l.url} placeholder="https://" onChange={(e) => set({ ...d, links: d.links.map((x, j) => j === i ? { ...x, url: e.target.value } : x) })} /></Field></div>
            {!disabled && <Rm label={`Remove link ${i + 1}`} onClick={() => set({ ...d, links: d.links.filter((_, j) => j !== i) })} />}
          </div>))}
        {!disabled && <Add onClick={() => set({ ...d, links: [...d.links, { label: "", url: "" }] })}>Add link</Add>}
        {!urlOk && <p className="text-[13px] text-danger">Links must start with https://</p>}
      </div>
    </div>
  );
}
