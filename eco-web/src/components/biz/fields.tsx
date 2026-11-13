"use client";
// Editors for the parts of a business profile that are lists. Used by onboarding and the profile page.
import { Plus, Trash2 } from "lucide-react";
import { CHANNELS, type BizCompetitor, type Category, type ChannelUse, type Goal, type Offer } from "@/lib/biz";
import { Button, Field, Input, Select, cx } from "../ui";

function Remove({ onClick, label }: { onClick: () => void; label: string }) {
  return <button type="button" onClick={onClick} aria-label={label}
    className="grid h-11 w-11 shrink-0 place-items-center self-end rounded-m text-muted hover:bg-sunken hover:text-danger"><Trash2 className="h-4 w-4" /></button>;
}

export function OffersEditor({ value, onChange, disabled }: { value: Offer[]; onChange: (v: Offer[]) => void; disabled?: boolean }) {
  const set = (i: number, o: Partial<Offer>) => onChange(value.map((x, j) => (j === i ? { ...x, ...o } : x)));
  return (
    <div className="flex flex-col gap-3">
      {value.map((o, i) => (
        <div key={i} className="flex flex-wrap gap-2 sm:flex-nowrap">
          <div className="min-w-0 flex-[2]"><Field label={`Product or service ${i + 1}`} htmlFor={`of-${i}`}>
            <Input id={`of-${i}`} disabled={disabled} value={o.name} onChange={(e) => set(i, { name: e.target.value })} placeholder="e.g. Small chops tray" /></Field></div>
          <div className="min-w-0 flex-1"><Field label="Price (optional)" htmlFor={`op-${i}`}>
            <Input id={`op-${i}`} disabled={disabled} value={o.price ?? ""} onChange={(e) => set(i, { price: e.target.value || null })} placeholder="e.g. NGN 25,000" /></Field></div>
          {!disabled && <Remove label={`Remove product ${i + 1}`} onClick={() => onChange(value.filter((_, j) => j !== i))} />}
        </div>
      ))}
      {!disabled && <div><Button type="button" variant="secondary" size="sm" icon={<Plus className="h-4 w-4" />}
        onClick={() => onChange([...value, { name: "", price: null }])}>Add product or service</Button></div>}
    </div>
  );
}

export function CompetitorsEditor({ value, onChange, disabled }: { value: BizCompetitor[]; onChange: (v: BizCompetitor[]) => void; disabled?: boolean }) {
  const set = (i: number, o: Partial<BizCompetitor>) => onChange(value.map((x, j) => (j === i ? { ...x, ...o } : x)));
  return (
    <div className="flex flex-col gap-3">
      {value.map((c, i) => (
        <div key={i} className="flex flex-wrap gap-2 rounded-m border border-line p-3 sm:flex-nowrap">
          <div className="min-w-0 flex-1"><Field label="Competitor name" htmlFor={`cn-${i}`}>
            <Input id={`cn-${i}`} disabled={disabled} value={c.name} onChange={(e) => set(i, { name: e.target.value })} /></Field></div>
          <div className="min-w-0 flex-[2]"><Field label="What you've noticed" htmlFor={`cno-${i}`}>
            <Input id={`cno-${i}`} disabled={disabled} value={c.notes ?? ""} onChange={(e) => set(i, { notes: e.target.value })} placeholder="Prices, strengths, complaints you've heard" /></Field></div>
          {!disabled && <Remove label={`Remove competitor ${i + 1}`} onClick={() => onChange(value.filter((_, j) => j !== i))} />}
        </div>
      ))}
      {!disabled && <div><Button type="button" variant="secondary" size="sm" icon={<Plus className="h-4 w-4" />}
        onClick={() => onChange([...value, { name: "", notes: "" }])}>Add competitor</Button></div>}
      <p className="text-[13px] text-muted">The AI only discusses competitors you name here. It can't look at their accounts, prices or ads for you.</p>
    </div>
  );
}

const STATUS: ChannelUse["status"][] = ["using", "tried", "considering"];
export function ChannelsEditor({ value, onChange, disabled }: { value: ChannelUse[]; onChange: (v: ChannelUse[]) => void; disabled?: boolean }) {
  const get = (id: string) => value.find((c) => c.channel === id);
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {CHANNELS.map((ch) => {
        const cur = get(ch.id);
        return (
          <div key={ch.id} className={cx("flex items-center justify-between gap-2 rounded-m border px-3 py-2", cur ? "border-orange bg-orange-soft" : "border-line bg-raised")}>
            <span className="text-[14px] font-semibold">{ch.label}</span>
            <Select aria-label={`${ch.label} status`} disabled={disabled} className="w-auto min-w-[140px]" value={cur?.status ?? ""}
              onChange={(e) => {
                const s = e.target.value as ChannelUse["status"] | "";
                const rest = value.filter((c) => c.channel !== ch.id);
                onChange(s ? [...rest, { channel: ch.id, status: s }] : rest);
              }}>
              <option value="">Not used</option>{STATUS.map((s) => <option key={s} value={s}>{s === "using" ? "Using now" : s === "tried" ? "Tried before" : "Considering"}</option>)}
            </Select>
          </div>
        );
      })}
    </div>
  );
}

export function GoalsEditor({ value, onChange, disabled }: { value: Goal[]; onChange: (v: Goal[]) => void; disabled?: boolean }) {
  const set = (i: number, o: Partial<Goal>) => onChange(value.map((x, j) => (j === i ? { ...x, ...o } : x)));
  return (
    <div className="flex flex-col gap-3">
      {value.map((g, i) => (
        <div key={i} className="grid gap-2 rounded-m border border-line p-3 sm:grid-cols-[2fr_1.4fr_1fr_auto]">
          <Field label={`Goal ${i + 1}`} htmlFor={`g-${i}`}><Input id={`g-${i}`} disabled={disabled} value={g.goal} onChange={(e) => set(i, { goal: e.target.value })} placeholder="e.g. More weekend party orders" /></Field>
          <Field label="How you'll measure it" htmlFor={`gm-${i}`}><Input id={`gm-${i}`} disabled={disabled} value={g.metric ?? ""} onChange={(e) => set(i, { metric: e.target.value })} placeholder="orders per weekend" /></Field>
          <Field label="Target" htmlFor={`gt-${i}`}><Input id={`gt-${i}`} disabled={disabled} value={g.target ?? ""} onChange={(e) => set(i, { target: e.target.value })} placeholder="20" /></Field>
          {!disabled && <Remove label={`Remove goal ${i + 1}`} onClick={() => onChange(value.filter((_, j) => j !== i))} />}
        </div>
      ))}
      {!disabled && value.length < 8 && <div><Button type="button" variant="secondary" size="sm" icon={<Plus className="h-4 w-4" />}
        onClick={() => onChange([...value, { goal: "", metric: "", target: "" }])}>Add goal</Button></div>}
    </div>
  );
}

export function CategoryGrid({ cats, value, onChange }: { cats: Category[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" role="radiogroup" aria-label="Business category">
      {cats.map((c) => (
        <button key={c.key} type="button" role="radio" aria-checked={value === c.key} onClick={() => onChange(c.key)}
          className={cx("rounded-m border-2 p-3 text-left transition", value === c.key ? "border-orange bg-orange-soft" : "border-line bg-raised hover:border-control")}>
          <div className="font-semibold">{c.label}</div><div className="mt-0.5 text-[13px] text-muted">{c.examples}</div>
        </button>
      ))}
    </div>
  );
}

/** Profile form state <-> API body. Empty rows are dropped so half-typed entries never fail validation. */
export type ProfileForm = {
  business_name: string; category: string; industry: string; sub_type: string; stage: string; business_model: "b2c" | "b2b" | "both";
  location: string; target_markets: string; website: string; offers: Offer[]; customers: string; differentiators: string;
  competitors: BizCompetitor[]; channels: ChannelUse[]; goals: Goal[]; budget_amount: string; currency: string; budget_notes: string;
};
export const emptyForm = (currency = ""): ProfileForm => ({ business_name: "", category: "", industry: "", sub_type: "", stage: "new",
  business_model: "b2c", location: "", target_markets: "", website: "", offers: [{ name: "", price: null }], customers: "",
  differentiators: "", competitors: [], channels: [], goals: [{ goal: "", metric: "", target: "" }], budget_amount: "", currency, budget_notes: "" });

export function toBody(f: ProfileForm, brand: Record<string, unknown> = {}) {
  return {
    business_name: f.business_name.trim(), category: f.category || "other", industry: f.industry.trim(), sub_type: f.sub_type.trim() || null,
    stage: f.stage, business_model: f.business_model, location: f.location.trim() || null,
    target_markets: f.target_markets.split(",").map((s) => s.trim()).filter(Boolean), website: f.website.trim() || null,
    offers: f.offers.filter((o) => o.name.trim()).map((o) => ({ name: o.name.trim(), price: o.price || null })),
    customers: f.customers.trim() || null, differentiators: f.differentiators.trim() || null,
    competitors: f.competitors.filter((c) => c.name.trim()).map((c) => ({ name: c.name.trim(), notes: c.notes ?? "" })),
    channels: f.channels, goals: f.goals.filter((g) => g.goal.trim()),
    budget: { monthly_amount: f.budget_amount === "" ? null : Number(f.budget_amount), currency: f.currency.toUpperCase(), notes: f.budget_notes },
    brand,
  };
}
export function fromProfile(p: any): ProfileForm { // eslint-disable-line @typescript-eslint/no-explicit-any
  return { business_name: p.business_name, category: p.category, industry: p.industry, sub_type: p.sub_type ?? "", stage: p.stage,
    business_model: p.business_model, location: p.location ?? "", target_markets: (p.target_markets ?? []).join(", "), website: p.website ?? "",
    offers: p.offers?.length ? p.offers : [{ name: "", price: null }], customers: p.customers ?? "", differentiators: p.differentiators ?? "",
    competitors: p.competitors ?? [], channels: p.channels ?? [], goals: p.goals?.length ? p.goals : [{ goal: "", metric: "", target: "" }],
    budget_amount: p.budget?.monthly_amount == null ? "" : String(p.budget.monthly_amount), currency: p.budget?.currency ?? "",
    budget_notes: p.budget?.notes ?? "" };
}
