"use client";
// Core interface components built on the New Age AI design system (cream canvas, black frame, orange action).
import { Check, Copy, Loader2, Sparkles, X, AlertTriangle, Info, CircleCheck } from "lucide-react";
import Link from "next/link";
import React, { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from "react";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

// ---------------------------------------------------------------- buttons
type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger"; size?: "sm" | "md"; loading?: boolean;
  icon?: React.ReactNode; ai?: boolean;
};
const BTN = {
  primary: "bg-orange text-on-orange hover:brightness-95 active:brightness-90",
  secondary: "bg-raised text-ink border border-control hover:bg-sunken",
  ghost: "text-ink hover:bg-sunken",
  danger: "bg-danger-soft text-danger border border-danger/40 hover:bg-danger/10",
};
export function Button({ variant = "primary", size = "md", loading, icon, ai, className, children, disabled, ...p }: BtnProps) {
  return (
    <button {...p} disabled={disabled || loading}
      className={cx("inline-flex items-center justify-center gap-2 rounded-m font-semibold transition duration-150",
        "disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98] min-h-[40px]",
        size === "sm" ? "px-3 py-1.5 text-[13px] min-h-[34px]" : "px-4 py-2 text-[14px]", BTN[variant], className)}>
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : ai ? <Sparkles className="h-4 w-4" aria-hidden /> : icon}
      {children}
    </button>
  );
}
export function LinkButton({ href, variant = "secondary", children, className, download }: {
  href: string; variant?: keyof typeof BTN; children: React.ReactNode; className?: string; download?: boolean }) {
  const cls = cx("inline-flex items-center gap-2 rounded-m px-4 py-2 text-[14px] font-semibold transition min-h-[40px]",
    BTN[variant], className);
  return download ? <a href={href} className={cls}>{children}</a> : <Link href={href} className={cls}>{children}</Link>;
}

// ---------------------------------------------------------------- surfaces
export function Card({ className, children, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return <div {...p} className={cx("rounded-m border border-line bg-raised p-5", className)}>{children}</div>;
}
export function PageHeader({ title, eyebrow, children, description }: {
  title: string; eyebrow?: string; description?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-[12px] font-semibold uppercase tracking-[0.6px] text-muted">{eyebrow}</div>}
        <h1 className="font-display text-[28px] font-[650] leading-[34px] tracking-[-0.3px]">{title}</h1>
        {description && <p className="mt-1 max-w-[65ch] text-muted">{description}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}
export function SectionTitle({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-2">
      <h2 className="text-[20px] font-semibold leading-7">{children}</h2>{right}
    </div>
  );
}

// ---------------------------------------------------------------- status & notices
const STATUS: Record<string, [string, string]> = {
  draft: ["Draft", "bg-sunken text-ink"], in_review: ["In review", "bg-warning-soft text-warning"],
  approved: ["Approved", "bg-success-soft text-success"], posted: ["Posted", "bg-d1-soft text-d1"],
  archived: ["Archived", "bg-sunken text-muted"], planned: ["Planned", "bg-sunken text-ink"],
  drafted: ["Drafted", "bg-orange-soft text-orange-text"], ready: ["Ready", "bg-success-soft text-success"],
  published_manually: ["Posted by you", "bg-d1-soft text-d1"], skipped: ["Skipped", "bg-sunken text-muted"],
  active: ["Active", "bg-success-soft text-success"], completed: ["Completed", "bg-d1-soft text-d1"],
  operational: ["Works now", "bg-success-soft text-success"], manual: ["Works with your data", "bg-warning-soft text-warning"],
  requires_integration: ["Needs integration", "bg-danger-soft text-danger"],
  partial: ["Partly available", "bg-warning-soft text-warning"], connect: ["Connect in Settings", "bg-success-soft text-success"],
  awaiting_approval: ["Awaiting approval", "bg-warning-soft text-warning"], rejected: ["Rejected", "bg-sunken text-muted"],
  executed: ["Done", "bg-success-soft text-success"], failed: ["Failed", "bg-danger-soft text-danger"],
  expired: ["Expired", "bg-sunken text-muted"], strong: ["Strong fit", "bg-success-soft text-success"],
  possible: ["Possible", "bg-warning-soft text-warning"], weak: ["Weak fit", "bg-sunken text-muted"],
  unverified: ["Not verified", "bg-warning-soft text-warning"], verified: ["Verified by you", "bg-success-soft text-success"],
  closed: ["Closed", "bg-sunken text-muted"], preparing: ["Preparing", "bg-sunken text-ink"],
  applied: ["Applied", "bg-orange-soft text-orange-text"], interviewing: ["Interviewing", "bg-d3-soft text-d3"],
  offer: ["Offer", "bg-success-soft text-success"], accepted: ["Accepted", "bg-success-soft text-success"],
  withdrawn: ["Withdrawn", "bg-sunken text-muted"], no_response: ["No response", "bg-sunken text-muted"],
  eligible: ["Eligible", "bg-success-soft text-success"], not_eligible: ["Not eligible", "bg-danger-soft text-danger"],
  unclear: ["Eligibility unclear", "bg-warning-soft text-warning"],
  in_progress: ["In progress", "bg-d3-soft text-d3"], done: ["Finished", "bg-success-soft text-success"],
};
export function StatusBadge({ status }: { status: string }) {
  const [label, cls] = STATUS[status] ?? [status.replace(/_/g, " "), "bg-sunken text-ink"];
  return <span className={cx("inline-flex items-center rounded-full px-2.5 py-0.5 text-[12px] font-semibold", cls)}>{label}</span>;
}
export function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "d1" | "d2" | "d3" | "orange" | "success" | "warning" | "danger" }) {
  const cls = { neutral: "bg-sunken text-ink", d1: "bg-d1-soft text-d1", d2: "bg-d2-soft text-d2", d3: "bg-d3-soft text-d3",
    orange: "bg-orange-soft text-orange-text", success: "bg-success-soft text-success", warning: "bg-warning-soft text-warning",
    danger: "bg-danger-soft text-danger" }[tone];
  return <span className={cx("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[12px] font-semibold", cls)}>{children}</span>;
}
export function Notice({ tone = "info", title, children }: {
  tone?: "info" | "warning" | "danger" | "success"; title?: string; children: React.ReactNode }) {
  const map = {
    info: ["bg-sunken text-ink", <Info key="i" className="h-4 w-4 shrink-0" />],
    warning: ["bg-warning-soft text-ink", <AlertTriangle key="w" className="h-4 w-4 shrink-0 text-warning" />],
    danger: ["bg-danger-soft text-ink", <AlertTriangle key="d" className="h-4 w-4 shrink-0 text-danger" />],
    success: ["bg-success-soft text-ink", <CircleCheck key="s" className="h-4 w-4 shrink-0 text-success" />],
  } as const;
  const [cls, icon] = map[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cx("flex gap-3 rounded-m p-3 text-[14px]", cls)}>
      <span className="mt-0.5">{icon}</span>
      <div className="min-w-0">{title && <div className="font-semibold">{title}</div>}<div>{children}</div></div>
    </div>
  );
}
export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton animate-shimmer rounded-s", className)} aria-hidden />;
}
export function EmptyState({ icon, title, children, action, tone = "d1" }: {
  icon?: React.ReactNode; title: string; children?: React.ReactNode; action?: React.ReactNode; tone?: "d1" | "d2" | "d3" }) {
  return (
    <div className="flex flex-col items-center rounded-m border border-dashed border-control/60 bg-raised/60 px-6 py-10 text-center">
      {icon && <div className={cx("mb-3 grid h-12 w-12 place-items-center rounded-full", tone === "d2" ? "bg-d2-soft text-d2" : tone === "d3" ? "bg-d3-soft text-d3" : "bg-d1-soft text-d1")}>{icon}</div>}
      <div className="text-[16px] font-semibold">{title}</div>
      {children && <p className="mt-1 max-w-[50ch] text-muted">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
export function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="rounded-m border border-line bg-raised p-4">
      <div className="text-[12px] font-semibold uppercase tracking-[0.6px] text-muted">{label}</div>
      <div className="mt-1 font-mono text-[28px] font-semibold leading-8 tracking-[-0.5px] tabular">{value}</div>
      {hint && <div className="mt-1 text-[13px] text-muted">{hint}</div>}
    </div>
  );
}

// ---------------------------------------------------------------- form controls
export function Field({ label, hint, error, children, htmlFor }: {
  label: string; hint?: string; error?: string; children: React.ReactNode; htmlFor?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-[14px] font-semibold">{label}</label>
      {children}
      {hint && !error && <div className="text-[13px] text-muted">{hint}</div>}
      {error && <div className="text-[13px] text-danger">{error}</div>}
    </div>
  );
}
const control = "w-full rounded-s border border-control bg-raised px-3 py-2 text-[15px] text-ink placeholder:text-muted " +
  "transition focus:border-ink";
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...p }, ref) { return <input ref={ref} {...p} className={cx(control, "min-h-[40px]", className)} />; });
export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...p }, ref) { return <textarea ref={ref} {...p} className={cx(control, "min-h-[88px]", className)} />; });
export function Select({ className, children, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...p} className={cx(control, "min-h-[40px] pr-8", className)}>{children}</select>;
}
export function Toggle({ on, onChange, children, disabled }: {
  on: boolean; onChange: (v: boolean) => void; children: React.ReactNode; disabled?: boolean }) {
  return (
    <button type="button" aria-pressed={on} disabled={disabled} onClick={() => onChange(!on)}
      className={cx("inline-flex min-h-[36px] items-center gap-1.5 rounded-full border px-3 py-1 text-[13px] font-semibold transition",
        on ? "border-orange bg-orange text-on-orange" : "border-control bg-raised text-ink hover:bg-sunken")}>
      {on && <Check className="h-3.5 w-3.5" aria-hidden />}{children}
    </button>
  );
}

// ---------------------------------------------------------------- overlays
export function Modal({ open, onClose, title, children, footer, wide }: {
  open: boolean; onClose: () => void; title: string; children: React.ReactNode; footer?: React.ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>("input,textarea,select,button")?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); prev?.focus(); };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-[#171717]/60 p-0 sm:items-center sm:p-6"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={id}
        className={cx("flex max-h-[92vh] w-full flex-col rounded-t-l bg-cream shadow-2 animate-rise sm:rounded-l",
          wide ? "sm:max-w-3xl" : "sm:max-w-lg")}>
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
          <h2 id={id} className="text-[16px] font-semibold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="grid h-9 w-9 place-items-center rounded-m hover:bg-sunken">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}
export function Drawer({ open, onClose, title, children, footer }: {
  open: boolean; onClose: () => void; title: string; children: React.ReactNode; footer?: React.ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-[#171717]/50" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside role="dialog" aria-modal="true" aria-label={title}
        className="flex h-full w-full max-w-xl flex-col bg-cream shadow-2 animate-rise">
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
          <h2 className="truncate text-[16px] font-semibold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="grid h-9 w-9 place-items-center rounded-m hover:bg-sunken"><X className="h-4 w-4" /></button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex flex-wrap gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </aside>
    </div>
  );
}

// ---------------------------------------------------------------- toasts
type ToastT = { id: number; text: string; tone: "success" | "danger" };
const ToastCtx = createContext<(text: string, tone?: "success" | "danger") => void>(() => {});
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastT[]>([]);
  const push = useCallback((text: string, tone: "success" | "danger" = "success") => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, text, tone }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), 4500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-20 left-1/2 z-[60] flex -translate-x-1/2 flex-col gap-2 lg:bottom-6" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={cx("pointer-events-auto rounded-m px-4 py-2.5 text-[14px] font-semibold shadow-1 animate-rise",
            t.tone === "success" ? "bg-ink text-cream" : "bg-danger text-cream")}>{t.text}</div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  return (
    <>
      <Button variant="secondary" size="sm" icon={done ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
        onClick={async () => {
          try { await navigator.clipboard.writeText(text); } catch {
            ref.current?.select(); document.execCommand?.("copy");
          }
          setDone(true); setTimeout(() => setDone(false), 1500);
        }}>{done ? "Copied" : label}</Button>
      <textarea ref={ref} readOnly value={text} className="sr-only" aria-hidden tabIndex={-1} />
    </>
  );
}

/** Two-step destructive action without browser dialogs. */
export function ConfirmButton({ onConfirm, children, label = "Are you sure?" }: {
  onConfirm: () => void | Promise<void>; children: React.ReactNode; label?: string }) {
  const [ask, setAsk] = useState(false);
  if (!ask) return <Button variant="ghost" size="sm" onClick={() => setAsk(true)}>{children}</Button>;
  return (
    <span className="inline-flex items-center gap-2 text-[13px]">
      {label}
      <Button variant="danger" size="sm" onClick={async () => { await onConfirm(); setAsk(false); }}>Yes</Button>
      <Button variant="ghost" size="sm" onClick={() => setAsk(false)}>No</Button>
    </span>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: {
  value: T; onChange: (v: T) => void; items: { id: T; label: string; count?: number }[] }) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto rounded-m bg-sunken p-1">
      {items.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={cx("flex min-h-[36px] shrink-0 items-center gap-2 rounded-s px-3 text-[14px] font-semibold transition",
            value === t.id ? "bg-raised text-ink shadow-1" : "text-muted hover:text-ink")}>
          {t.label}{t.count !== undefined && <span className="font-mono text-[12px] text-muted">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- safe markdown (no HTML injection: React nodes only)
function inline(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|_[^_]+_|\[[^\]]+\]\(https?:\/\/[^)\s]+\))/g;
  let last = 0; let m: RegExpExecArray | null; let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const t = m[0];
    if (t.startsWith("**")) parts.push(<strong key={i++}>{t.slice(2, -2)}</strong>);
    else if (t.startsWith("_")) parts.push(<em key={i++}>{t.slice(1, -1)}</em>);
    else {
      const [, label, href] = /\[([^\]]+)\]\(([^)]+)\)/.exec(t)!;
      parts.push(<a key={i++} href={href} target="_blank" rel="noopener noreferrer nofollow" className="text-orange-text underline">{label}</a>);
    }
    last = m.index + t.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}
export function Markdown({ text, className }: { text: string; className?: string }) {
  const lines = text.split("\n");
  const out: React.ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (l.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        const cells = lines[i].replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
        if (!cells.every((c) => /^:?-+:?$/.test(c))) rows.push(cells);
        i++;
      }
      out.push(
        <div key={out.length} className="my-2 overflow-x-auto"><table className="w-full text-[13px]">
          <thead><tr>{rows[0]?.map((c, j) => <th key={j} className="border-b border-line bg-sunken px-2 py-1 text-left">{inline(c)}</th>)}</tr></thead>
          <tbody>{rows.slice(1).map((r, k) => <tr key={k}>{r.map((c, j) => <td key={j} className="border-b border-line px-2 py-1 tabular">{inline(c)}</td>)}</tr>)}</tbody>
        </table></div>);
      continue;
    }
    if (/^[-*] /.test(l)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*] /.test(lines[i])) items.push(lines[i++].slice(2));
      out.push(<ul key={out.length} className="my-1 list-disc space-y-1 pl-5">{items.map((t, k) => <li key={k}>{inline(t)}</li>)}</ul>);
      continue;
    }
    if (l.startsWith("### ")) out.push(<h4 key={out.length} className="mt-3 text-[15px] font-semibold">{inline(l.slice(4))}</h4>);
    else if (l.startsWith("## ")) out.push(<h3 key={out.length} className="mt-3 text-[16px] font-semibold">{inline(l.slice(3))}</h3>);
    else if (l.startsWith("> ")) out.push(<blockquote key={out.length} className="my-1 border-l-2 border-orange pl-3 italic">{inline(l.slice(2))}</blockquote>);
    else if (l.trim()) out.push(<p key={out.length} className="my-1.5">{inline(l)}</p>);
    i++;
  }
  return <div className={cx("break-words", className)}>{out}</div>;
}

export function fmtDate(d: string | Date, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" }) {
  return new Date(d).toLocaleDateString("en-GB", opts);
}
export function fmtTime(d: string | Date) {
  return new Date(d).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}
export const num = (n: number | null | undefined) => (n === null || n === undefined ? "–" : n.toLocaleString("en-GB"));
