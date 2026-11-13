"use client";
import { ArrowRight, BriefcaseBusiness, Megaphone, UserRoundSearch } from "lucide-react";
import Link from "next/link";
import { useApi } from "@/lib/api";
import type { OnboardingState } from "@/lib/types";
import { TopBar } from "@/components/TopBar";
import { Skeleton, cx } from "@/components/ui";

type BizState = { businesses: { workspace_id: string }[] };

export default function Start() {
  const c = useApi<OnboardingState>("/v1/creator/onboarding");
  const b = useApi<BizState>("/v1/business/onboarding");
  const f = useApi<{ workspace_id: string | null }>("/v1/freelancer/onboarding");
  const nC = c.data?.clients.length ?? 0, nB = b.data?.businesses.length ?? 0;
  const cards = [
    { key: "creator", icon: Megaphone, tint: "bg-d1-soft text-d1", title: "Creator & Marketing",
      who: "Creators, social media managers, freelancers and agencies",
      what: "Client workspaces, content studio, calendar, approvals and client reports.",
      href: nC ? (nC === 1 ? `/c/${c.data!.clients[0].workspace_id}` : "/clients") : "/onboarding",
      cta: nC ? `Open (${nC} client${nC === 1 ? "" : "s"})` : "Set up" },
    { key: "business", icon: BriefcaseBusiness, tint: "bg-d2-soft text-d2", title: "Business Marketing",
      who: "Entrepreneurs, startups, SMEs and established businesses",
      what: "Your Marketing Intelligence Profile, strategy, plans, ads, growth and results.",
      href: nB ? (nB === 1 ? `/b/${b.data!.businesses[0].workspace_id}` : "/businesses") : "/business/onboarding",
      cta: nB ? `Open (${nB} business${nB === 1 ? "" : "es"})` : "Set up" },
    { key: "freelancer", icon: UserRoundSearch, tint: "bg-d3-soft text-d3", title: "Freelancer Growth",
      who: "Freelancers, remote workers and independent professionals",
      what: "Your professional profile, CVs, proposals, interview practice, opportunities and pricing.",
      href: f.data?.workspace_id ? `/f/${f.data.workspace_id}` : "/freelancer/onboarding",
      cta: f.data?.workspace_id ? "Open" : "Set up" },
  ];
  return (
    <div className="min-h-screen">
      <TopBar />
      <main className="mx-auto max-w-5xl px-4 py-10 sm:px-8">
        <h1 className="font-display text-[32px] font-bold leading-[38px] tracking-[-0.5px]">What are you working on?</h1>
        <p className="mt-2 max-w-[60ch] text-muted">One account, separate workspaces. Pick a product; you can use more than one.</p>
        {(!c.data || !b.data || !f.data) && !c.error && <div className="mt-8 grid gap-4 lg:grid-cols-3"><Skeleton className="h-56" /><Skeleton className="h-56" /><Skeleton className="h-56" /></div>}
        {c.data && b.data && f.data && (
          <div className="mt-8 grid gap-4 lg:grid-cols-3">
            {cards.map(({ key, icon: Icon, tint, title, who, what, href, cta }) => (
              <Link key={key} href={href} className="group flex flex-col rounded-l border border-line bg-raised p-6 transition hover:-translate-y-0.5 hover:border-control hover:shadow-1">
                <span className={cx("grid h-12 w-12 place-items-center rounded-full", tint)}><Icon className="h-6 w-6" /></span>
                <h2 className="mt-4 font-display text-[22px] font-semibold">{title}</h2>
                <p className="mt-1 text-[14px] font-semibold text-muted">{who}</p>
                <p className="mt-3 flex-1 text-[15px]">{what}</p>
                <span className="mt-5 inline-flex items-center gap-1 font-semibold text-orange-text group-hover:underline">{cta}<ArrowRight className="h-4 w-4" /></span>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
