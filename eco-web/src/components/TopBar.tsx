"use client";
import { LogOut } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Logo } from "./Logo";

export function TopBar() {
  return (
    <header className="flex items-center justify-between bg-sidebar px-4 py-3 sm:px-8">
      <Link href="/start" aria-label="Choose a product"><Logo inverse /></Link>
      <button onClick={async () => { await api.auth("logout").catch(() => 0); location.href = "/login"; }}
        className="inline-flex min-h-[40px] items-center gap-2 rounded-m px-3 text-[14px] font-semibold text-sidebar-ink hover:bg-sidebar-hover">
        <LogOut className="h-4 w-4" />Sign out</button>
    </header>
  );
}
