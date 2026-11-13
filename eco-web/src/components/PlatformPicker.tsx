"use client";
import { PLATFORMS, type Platform } from "@/lib/types";
import { Toggle } from "./ui";

export function PlatformPicker({ value, onChange, only }: { value: string[]; onChange: (v: Platform[]) => void; only?: string[] }) {
  const list = only?.length ? PLATFORMS.filter((p) => only.includes(p.id)) : PLATFORMS;
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Platforms">
      {list.map((p) => (
        <Toggle key={p.id} on={value.includes(p.id)}
          onChange={(on) => onChange((on ? [...value, p.id] : value.filter((x) => x !== p.id)) as Platform[])}>{p.label}</Toggle>
      ))}
    </div>
  );
}
