"use client";
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError, errorText, put, useApi } from "@/lib/api";
import type { ClientProfile, Platform } from "@/lib/types";
import { PLATFORMS } from "@/lib/types";
import { PlatformPicker } from "@/components/PlatformPicker";
import { useWs } from "@/components/Shell";
import { BrandForm, BrandResult, Generating, useGenerate } from "@/components/studio";
import { Button, Card, Field, Input, Modal, Notice, PageHeader, SectionTitle, Select, Skeleton, Textarea, useToast } from "@/components/ui";

const EMPTY: ClientProfile = { client_name: "", industry: "", website: "", business_info: { description: "", offers: [], location: "" },
  platforms: [], brand_voice: {}, audience: { summary: "", personas: [], locations: [] }, goals: [], competitors: [], content_pillars: [], notes: "" };
const csv = (v: unknown) => (Array.isArray(v) ? v.join(", ") : typeof v === "string" ? v : "");
const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

type Col<T> = { key: keyof T; label: string; kind?: "text" | "area" | "platform" | "date" | "list"; wide?: boolean };
function ListEditor<T extends Record<string, unknown>>({ label, rows, cols, blank, onChange, disabled, max = 10 }: {
  label: string; rows: T[]; cols: Col<T>[]; blank: T; onChange: (r: T[]) => void; disabled?: boolean; max?: number }) {
  const set = (i: number, k: keyof T, v: unknown) => onChange(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <div className="flex flex-col gap-3">
      {rows.map((r, i) => (
        <div key={i} className="grid gap-3 rounded-m border border-line bg-cream/50 p-3 sm:grid-cols-2">
          {cols.map((c) => {
            const id = `${label}-${i}-${String(c.key)}`;
            const v = r[c.key];
            return (
              <div key={String(c.key)} className={c.wide || c.kind === "area" ? "sm:col-span-2" : ""}>
                <Field label={c.label} htmlFor={id}>
                  {c.kind === "area" ? <Textarea id={id} rows={2} disabled={disabled} value={(v as string) ?? ""} onChange={(e) => set(i, c.key, e.target.value)} />
                    : c.kind === "platform" ? <Select id={id} disabled={disabled} value={(v as string) ?? ""} onChange={(e) => set(i, c.key, e.target.value || null)}>
                      <option value="">—</option>{PLATFORMS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</Select>
                    : c.kind === "list" ? <Input id={id} disabled={disabled} value={csv(v)} onChange={(e) => set(i, c.key, split(e.target.value))} placeholder="Comma separated" />
                    : <Input id={id} type={c.kind === "date" ? "date" : "text"} disabled={disabled} value={(v as string) ?? ""} onChange={(e) => set(i, c.key, e.target.value || (c.kind === "date" ? null : ""))} />}
                </Field>
              </div>
            );
          })}
          {!disabled && <div className="sm:col-span-2"><Button variant="ghost" size="sm" icon={<Trash2 className="h-4 w-4" />} onClick={() => onChange(rows.filter((_, j) => j !== i))}>Remove</Button></div>}
        </div>
      ))}
      {!disabled && rows.length < max && <div><Button variant="secondary" size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => onChange([...rows, { ...blank }])}>Add {label}</Button></div>}
    </div>
  );
}

export default function Brand() {
  const { ws, canWrite } = useWs();
  const toast = useToast();
  const prof = useApi<ClientProfile>(`/v1/workspaces/${ws.id}/client-account`);
  const [p, setP] = useState<ClientProfile>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ai, setAi] = useState(false);
  const g = useGenerate();
  useEffect(() => { if (prof.data) setP({ ...EMPTY, ...prof.data }); else if (prof.error instanceof ApiError && prof.error.status === 404) setP({ ...EMPTY, client_name: ws.name }); }, [prof.data, prof.error, ws.name]);
  const v = p.brand_voice as Record<string, any>;
  const setV = (k: string, val: unknown) => setP({ ...p, brand_voice: { ...p.brand_voice, [k]: val } });
  const dis = !canWrite;

  async function save() {
    setBusy(true); setErr("");
    try {
      const { version, updated_at, ...body } = p as ClientProfile & { id?: string };
      delete (body as Record<string, unknown>).id;
      await put(`/v1/workspaces/${ws.id}/client-account`, { ...body, website: body.website || null, industry: body.industry || null,
        goals: body.goals.map((g) => ({ ...g, due: g.due || null })) });
      toast("Profile saved"); prof.reload();
    } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  }
  if (!prof.data && !prof.error) return <Skeleton className="h-96" />;

  return (
    <div>
      <PageHeader title="Brand & audience" description="Everything the AI knows about this client comes from here, so the more complete it is, the better the drafts.">
        <Button ai variant="secondary" disabled={dis} onClick={() => setAi(true)}>Build voice with AI</Button>
        <Button onClick={save} loading={busy} disabled={dis || !p.client_name.trim()}>Save profile</Button>
      </PageHeader>
      {err && <div className="mb-4"><Notice tone="danger">{err}</Notice></div>}
      <div className="grid gap-6 xl:grid-cols-2">
        <Card className="flex flex-col gap-4">
          <SectionTitle>Business</SectionTitle>
          <Field label="Client or brand name" htmlFor="bn"><Input id="bn" disabled={dis} value={p.client_name} onChange={(e) => setP({ ...p, client_name: e.target.value })} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Industry" htmlFor="bi"><Input id="bi" disabled={dis} value={p.industry ?? ""} onChange={(e) => setP({ ...p, industry: e.target.value })} /></Field>
            <Field label="Website" htmlFor="bw"><Input id="bw" disabled={dis} value={p.website ?? ""} placeholder="https://" onChange={(e) => setP({ ...p, website: e.target.value })} /></Field>
          </div>
          <Field label="What they do" htmlFor="bd"><Textarea id="bd" disabled={dis} value={p.business_info.description} onChange={(e) => setP({ ...p, business_info: { ...p.business_info, description: e.target.value } })} /></Field>
          <Field label="Location" htmlFor="bl"><Input id="bl" disabled={dis} value={p.business_info.location} onChange={(e) => setP({ ...p, business_info: { ...p.business_info, location: e.target.value } })} /></Field>
          <Field label="Platforms"><PlatformPicker value={p.platforms} onChange={(pl) => !dis && setP({ ...p, platforms: pl as Platform[] })} /></Field>
          <div><div className="mb-2 text-[14px] font-semibold">Products & offers</div>
            <ListEditor label="offer" disabled={dis} rows={p.business_info.offers as Record<string, unknown>[] as any} blank={{ name: "", price: "" } as any}
              cols={[{ key: "name", label: "Name" }, { key: "price", label: "Price as they state it" }]}
              onChange={(r) => setP({ ...p, business_info: { ...p.business_info, offers: r as any } })} max={30} /></div>
        </Card>

        <Card className="flex flex-col gap-4">
          <SectionTitle>Brand voice</SectionTitle>
          <Field label="Positioning" htmlFor="vp"><Textarea id="vp" disabled={dis} value={v.positioning ?? ""} onChange={(e) => setV("positioning", e.target.value)} /></Field>
          <Field label="Tone" htmlFor="vt" hint="e.g. warm, witty, clear"><Input id="vt" disabled={dis} value={csv(v.traits ?? v.tone)} onChange={(e) => setV("traits", split(e.target.value))} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Words to use" htmlFor="vu"><Input id="vu" disabled={dis} value={csv(v.words_to_use)} onChange={(e) => setV("words_to_use", split(e.target.value))} /></Field>
            <Field label="Words to avoid" htmlFor="va"><Input id="va" disabled={dis} value={csv(v.words_to_avoid)} onChange={(e) => setV("words_to_avoid", split(e.target.value))} /></Field>
          </div>
          <Field label="Sample lines" htmlFor="vs" hint="One per line. Sentences that sound exactly like the brand.">
            <Textarea id="vs" disabled={dis} rows={3} value={(v.sample_lines ?? []).join("\n")} onChange={(e) => setV("sample_lines", e.target.value.split("\n").filter((x) => x.trim()))} /></Field>
          {Array.isArray(v.attributes) && v.attributes.length > 0 && (
            <div><div className="mb-2 text-[14px] font-semibold">Voice traits</div>
              <ListEditor label="trait" disabled={dis} rows={v.attributes} blank={{ trait: "", what_it_means: "", avoid: "" }}
                cols={[{ key: "trait", label: "Trait" }, { key: "avoid", label: "Not" }, { key: "what_it_means", label: "What it means", kind: "area" }]}
                onChange={(r) => setV("attributes", r)} /></div>
          )}
        </Card>

        <Card className="flex flex-col gap-4">
          <SectionTitle>Audience</SectionTitle>
          <Field label="Who they're for" htmlFor="as"><Textarea id="as" disabled={dis} value={p.audience.summary} onChange={(e) => setP({ ...p, audience: { ...p.audience, summary: e.target.value } })} /></Field>
          <div><div className="mb-2 text-[14px] font-semibold">Personas</div>
            <ListEditor label="persona" disabled={dis} rows={p.audience.personas as any} blank={{ name: "", description: "", needs: [], where_they_spend_time: [] } as any}
              cols={[{ key: "name", label: "Name" }, { key: "needs", label: "Needs", kind: "list" }, { key: "description", label: "Description", kind: "area" }]}
              onChange={(r) => setP({ ...p, audience: { ...p.audience, personas: r as any } })} max={6} /></div>
        </Card>

        <Card className="flex flex-col gap-4">
          <SectionTitle>Goals & content pillars</SectionTitle>
          <ListEditor label="goal" disabled={dis} rows={p.goals as any} blank={{ goal: "", metric: "", due: null } as any}
            cols={[{ key: "goal", label: "Goal", wide: true }, { key: "metric", label: "How you'll measure it" }, { key: "due", label: "By", kind: "date" }]}
            onChange={(r) => setP({ ...p, goals: r as any })} />
          <div><div className="mb-2 text-[14px] font-semibold">Content pillars</div>
            <ListEditor label="pillar" disabled={dis} rows={p.content_pillars as any} blank={{ name: "", purpose: "", example_topics: [] } as any}
              cols={[{ key: "name", label: "Pillar" }, { key: "example_topics", label: "Example topics", kind: "list" }, { key: "purpose", label: "Purpose", kind: "area" }]}
              onChange={(r) => setP({ ...p, content_pillars: r as any })} max={8} /></div>
        </Card>

        <Card className="flex flex-col gap-4 xl:col-span-2">
          <SectionTitle>Competitors</SectionTitle>
          <p className="text-[14px] text-muted">Add what your team has observed. The research tool analyses these notes; it can't look at their accounts for you.</p>
          <ListEditor label="competitor" disabled={dis} rows={p.competitors as any} blank={{ name: "", handle: "", platform: null, notes: "" } as any}
            cols={[{ key: "name", label: "Name" }, { key: "handle", label: "Handle" }, { key: "platform", label: "Main platform", kind: "platform" }, { key: "notes", label: "What you've noticed", kind: "area" }]}
            onChange={(r) => setP({ ...p, competitors: r as any })} />
        </Card>
      </div>
      <div className="mt-6 flex justify-end"><Button onClick={save} loading={busy} disabled={dis || !p.client_name.trim()}>Save profile</Button></div>

      <Modal open={ai} wide onClose={() => { setAi(false); g.setResult(null); }} title="Build the brand voice with AI">
        {!g.result && !g.busy && <BrandForm onRun={g.run} busy={g.busy} />}
        {g.error && <div className="mt-3"><Notice tone="danger">{g.error}</Notice></div>}
        {g.busy && <Generating label="Building the brand voice…" />}
        {g.result && (g.result.run.status === "succeeded" ? <BrandResult ex={g.result} onApplied={prof.reload} />
          : <Notice tone="warning">{g.result.assistant_message.content}</Notice>)}
      </Modal>
    </div>
  );
}
