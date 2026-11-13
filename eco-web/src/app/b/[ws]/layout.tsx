"use client";
import { useParams } from "next/navigation";
import { BUSINESS } from "@/components/divisions";
import { Shell } from "@/components/Shell";

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const { ws } = useParams<{ ws: string }>();
  return <Shell wsId={ws} division={BUSINESS}>{children}</Shell>;
}
