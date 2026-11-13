"use client";
import { useParams } from "next/navigation";
import { FREELANCER } from "@/components/divisions";
import { Shell } from "@/components/Shell";

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const { ws } = useParams<{ ws: string }>();
  return <Shell wsId={ws} division={FREELANCER}>{children}</Shell>;
}
