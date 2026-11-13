"use client";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { TOOLS } from "@/lib/biz";
import { useWs } from "@/components/Shell";
import { PageHeader } from "@/components/ui";

export default function Tools() {
  const { base } = useWs();
  return (
    <div className="flex flex-col gap-8">
      <PageHeader title="Strategy tools" description="Each tool reads your business profile and shapes its advice to your category, stage, location and budget. Everything it makes is editable and saveable." />
      {(["Understand", "Plan", "Grow"] as const).map((g) => (
        <section key={g}>
          <h2 className="mb-3 text-[12px] font-semibold uppercase tracking-[0.6px] text-muted">{g}</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {TOOLS.filter((t) => t.group === g).map((t) => (
              <Link key={t.key} href={`${base}/tools/${t.key}`} className="group flex flex-col rounded-m border border-line bg-raised p-5 transition hover:-translate-y-0.5 hover:border-control hover:shadow-1">
                <div className="font-semibold">{t.title}</div><p className="mt-1 flex-1 text-[14px] text-muted">{t.blurb}</p>
                <span className="mt-3 inline-flex items-center gap-1 text-[14px] font-semibold text-orange-text group-hover:underline">Open<ArrowRight className="h-4 w-4" /></span>
              </Link>))}
          </div>
        </section>))}
    </div>
  );
}
