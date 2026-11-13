"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { OnboardingState } from "@/lib/types";
import { Skeleton } from "@/components/ui";

type BizState = { businesses: { workspace_id: string }[] };

/** Send people to the product they use; if they use none or both, let them choose. */
export default function Home() {
  const router = useRouter();
  useEffect(() => {
    Promise.all([api.get<OnboardingState>("/v1/creator/onboarding"), api.get<BizState>("/v1/business/onboarding"),
      api.get<{ workspace_id: string | null }>("/v1/freelancer/onboarding")])
      .then(([c, b, f]) => {
        const hasC = c.clients.length > 0, hasB = b.businesses.length > 0, hasF = !!f.workspace_id;
        if (Number(hasC) + Number(hasB) + Number(hasF) !== 1) router.replace("/start");
        else if (hasC) router.replace(c.clients.length === 1 ? `/c/${c.clients[0].workspace_id}` : "/clients");
        else if (hasB) router.replace(b.businesses.length === 1 ? `/b/${b.businesses[0].workspace_id}` : "/businesses");
        else router.replace(`/f/${f.workspace_id}`);
      }).catch(() => router.replace("/login"));
  }, [router]);
  return <div className="mx-auto max-w-md p-10"><Skeleton className="h-8 w-48" /><Skeleton className="mt-4 h-24 w-full" /></div>;
}
