"use client";
import { ChevronDown, LogOut, Menu, Users } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import React, { createContext, useContext, useEffect, useState } from "react";
import { api, useApi } from "@/lib/api";
import { type Division, type SwitchRow } from "./divisions";
import { Logo } from "./Logo";
import { Notice, Skeleton, cx } from "./ui";

type WsInfo = { id: string; name: string; org_id: string; product: string; role: string; read_only: boolean };
type Ctx = { ws: WsInfo; rows: SwitchRow[]; canWrite: boolean; isAdmin: boolean; base: string; division: Division };
const WsCtx = createContext<Ctx | null>(null);
export const useWs = () => {
  const c = useContext(WsCtx);
  if (!c) throw new Error("useWs outside a workspace");
  return c;
};



function NavLinks({ base, division, onNavigate }: { base: string; division: Division; onNavigate?: () => void }) {
  const path = usePathname();
  return (
    <nav aria-label="Workspace" className="flex flex-col gap-5">
      {division.nav.map((s) => (
        <div key={s.section}>
          <div className="mb-1.5 px-3 text-[12px] font-semibold uppercase tracking-[0.6px] text-sidebar-muted">{s.section}</div>
          {s.items.map(({ href, label, icon: Icon }) => {
            const full = base + href;
            const active = href === "" ? path === base : path.startsWith(full);
            return (
              <Link key={label} href={full} onClick={onNavigate} aria-current={active ? "page" : undefined}
                className={cx("relative flex min-h-[40px] items-center gap-3 rounded-m px-3 text-[14px] font-semibold transition",
                  active ? "bg-sidebar-hover text-sidebar-ink" : "text-sidebar-ink/85 hover:bg-sidebar-hover")}>
                {active && <span className="absolute left-0 top-2 bottom-2 w-1 rounded-full bg-orange" aria-hidden />}
                <Icon className="h-[18px] w-[18px]" aria-hidden />{label}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

function Switcher({ ws, rows, division }: { ws: WsInfo; rows: SwitchRow[]; division: Division }) {
  const router = useRouter();
  const path = usePathname();
  const current = rows.find((c) => c.workspace_id === ws.id);
  return (
    <div className="relative">
      <div className="mb-1.5 px-1 text-[12px] font-semibold uppercase tracking-[0.6px] text-sidebar-muted">{division.name}</div>
      <label htmlFor="ws-switch" className="sr-only">Switch {division.noun}</label>
      <select id="ws-switch" value={ws.id}
        onChange={(e) => e.target.value === "__all" ? router.push(division.allHref)
          : router.push(path.replace(ws.id, e.target.value))}
        className="w-full appearance-none rounded-m border border-sidebar-hover bg-sidebar-hover py-2.5 pl-3 pr-8 text-[14px] font-semibold text-sidebar-ink">
        {rows.map((c) => <option key={c.workspace_id} value={c.workspace_id}>{c.label}</option>)}
        <option value="__all">{division.allLabel}…</option>
      </select>
      <ChevronDown className="pointer-events-none absolute bottom-3 right-2.5 h-4 w-4 text-sidebar-muted" aria-hidden />
      {current && current.org_kind === "team" && <div className="mt-1 px-1 text-[12px] text-sidebar-muted">{current.org_name}</div>}
    </div>
  );
}

async function signOut() {
  await api.auth("logout").catch(() => undefined);
  location.href = "/login";
}

export function Shell({ wsId, division, children }: { wsId: string; division: Division; children: React.ReactNode }) {
  const ws = useApi<WsInfo>(`/v1/workspaces/${wsId}`);
  const list = useApi<unknown>(division.listUrl);
  const [menu, setMenu] = useState(false);
  const path = usePathname();
  useEffect(() => { setMenu(false); }, [path]);
  const base = `${division.root}/${wsId}`;
  // Page title names the page, client/workspace and product (QA BUG-13; WCAG 2.4.2)
  useEffect(() => {
    const items = division.nav.flatMap((s) => s.items);
    const hit = items.filter((i) => (i.href === "" ? path === base : path.startsWith(base + i.href)))
      .sort((a, b) => b.href.length - a.href.length)[0];
    document.title = [hit?.label, ws.data?.name, division.name].filter(Boolean).join(" · ");
  }, [path, base, division, ws.data?.name]);
  const all = <Link className="underline" href={division.allHref}>{division.allLabel}</Link>;

  if (ws.error) {
    return <div className="mx-auto max-w-lg p-10"><Notice tone="danger" title={`Can't open this ${division.noun}`}>
      It may not exist or you may not have access. See {all}.</Notice></div>;
  }
  if (!ws.data || !list.data) {
    return <div className="flex min-h-screen"><div className="hidden w-[248px] bg-sidebar lg:block" />
      <div className="flex-1 p-8"><Skeleton className="h-8 w-64" /><Skeleton className="mt-6 h-40 w-full" /></div></div>;
  }
  if (ws.data.product !== division.product) {
    const other = ({ creator: "/c", business: "/b", freelancer: "/f" } as Record<string, string>)[ws.data.product] ?? null;
    return <div className="mx-auto max-w-lg p-10"><Notice tone="warning" title={`Not a ${division.name} workspace`}>
      This workspace belongs to another product.{" "}
      {other ? <Link className="underline" href={`${other}/${wsId}`}>Open it there</Link> : all}.</Notice></div>;
  }
  const rows = division.rows(list.data);
  const value: Ctx = { ws: ws.data, rows, base, division, isAdmin: ws.data.role === "admin",
    canWrite: (ws.data.role === "admin" || ws.data.role === "editor") && !ws.data.read_only };

  const sidebar = (
    <div className="flex h-full flex-col gap-6 p-4">
      <Link href="/start" className="px-1" aria-label="Choose a product"><Logo inverse division={division.product} /></Link>
      {division.switcher === false
        ? <div className="px-1"><div className="text-[12px] font-semibold uppercase tracking-[0.6px] text-sidebar-muted">{division.name}</div></div>
        : <Switcher ws={ws.data} rows={rows} division={division} />}
      <div className="flex-1 overflow-y-auto"><NavLinks base={base} division={division} onNavigate={() => setMenu(false)} /></div>
      <div className="flex flex-col gap-1 border-t border-sidebar-hover pt-3">
        <Link href={division.allHref} className="flex min-h-[40px] items-center gap-3 rounded-m px-3 text-[14px] font-semibold text-sidebar-ink/85 hover:bg-sidebar-hover">
          <Users className="h-[18px] w-[18px]" />{division.allLabel}</Link>
        <button onClick={signOut} className="flex min-h-[40px] items-center gap-3 rounded-m px-3 text-left text-[14px] font-semibold text-sidebar-ink/85 hover:bg-sidebar-hover">
          <LogOut className="h-[18px] w-[18px]" />Sign out</button>
      </div>
    </div>
  );

  return (
    <WsCtx.Provider value={value}>
      <div className="flex min-h-screen">
        <aside className="fixed inset-y-0 left-0 hidden w-[248px] bg-sidebar lg:block">{sidebar}</aside>
        {menu && (
          <div className="fixed inset-0 z-40 bg-[#171717]/60 lg:hidden" onMouseDown={(e) => e.target === e.currentTarget && setMenu(false)}>
            <aside className="h-full w-[280px] bg-sidebar animate-rise">{sidebar}</aside>
          </div>
        )}
        <div className="flex min-w-0 flex-1 flex-col lg:pl-[248px]">
          <header className="sticky top-0 z-30 flex items-center justify-between gap-3 bg-sidebar px-4 py-3 lg:hidden">
            <Logo inverse division={division.product} />
            <button onClick={() => setMenu(true)} aria-label="Open menu" className="grid h-11 w-11 place-items-center rounded-m text-sidebar-ink hover:bg-sidebar-hover">
              <Menu className="h-5 w-5" /></button>
          </header>
          {ws.data.read_only && (
            <div className="px-4 pt-4 sm:px-8"><Notice tone="warning" title="Read-only">
              Your plan includes fewer workspaces than you have, so this one can be viewed but not edited.</Notice></div>
          )}
          <main className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-6 pb-24 sm:px-8 sm:py-8 lg:pb-10">{children}</main>
        </div>
        <nav aria-label="Quick" className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-line bg-raised sm:hidden">
          {division.mobile.map((h) => {
            const item = division.nav.flatMap((s) => s.items).find((i) => i.href === h)!;
            const Icon = item.icon;
            const active = h === "" ? path === base : path.startsWith(base + h);
            return <Link key={h} href={base + h} className={cx("flex min-h-[56px] flex-col items-center justify-center gap-0.5 text-[11px] font-semibold",
              active ? "text-orange-text" : "text-muted")}><Icon className="h-5 w-5" />{item.short ?? item.label}</Link>;
          })}
          <button onClick={() => setMenu(true)} className="flex min-h-[56px] flex-col items-center justify-center gap-0.5 text-[11px] font-semibold text-muted">
            <Menu className="h-5 w-5" />More</button>
        </nav>
      </div>
    </WsCtx.Provider>
  );
}
