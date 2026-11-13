"use client";
import { ShieldAlert } from "lucide-react";
import type { RunSummary } from "@/lib/types";
import { Notice } from "./ui";

/** Everything the assistant flagged, shown with every AI result so nothing uncertain looks certain. */
export function RunPanel({ run }: { run: RunSummary }) {
  if (run.status === "clarify") return <Notice tone="info" title="The assistant needs a bit more">Answer its question to continue.</Notice>;
  if (run.status === "unsupported") return <Notice tone="warning" title="Not something this assistant can do">See its reply for what it can do instead.</Notice>;
  return (
    <div className="flex flex-col gap-2">
      {run.injection_detected && (
        <Notice tone="danger" title="Ignored instructions in your content">
          A document or source contained text aimed at the AI. It was treated as data and nothing was done because of it.
        </Notice>
      )}
      {run.uncertainties.length > 0 && (
        <Notice tone="warning" title="Check these before using it">
          <ul className="list-disc pl-5">{run.uncertainties.map((u, i) => <li key={i}>{u}</li>)}</ul>
        </Notice>
      )}
      {run.warnings.length > 0 && (
        <Notice tone="info" title="Notes"><ul className="list-disc pl-5">{run.warnings.map((u, i) => <li key={i}>{u}</li>)}</ul></Notice>
      )}
      {run.pending_actions.length > 0 && (
        <Notice tone="info" title="Waiting for approval">
          <span className="inline-flex items-center gap-1"><ShieldAlert className="h-4 w-4" />
            {run.pending_actions.length} proposed action(s). Nothing has been posted, sent or paid.</span>
        </Notice>
      )}
    </div>
  );
}
