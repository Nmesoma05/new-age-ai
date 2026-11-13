// Renders src/content/legal/*.md (a small, safe subset: headings, paragraphs, bullet lists, tables, **bold**) as React
// elements, with no raw HTML. A file still marked DRAFT shows a banner; the production pipeline refuses to deploy it.
import fs from "node:fs";
import path from "node:path";
import Link from "next/link";
import { Logo } from "@/components/Logo";

const DRAFT = "<!-- DRAFT";

function inline(s: string, key: string): React.ReactNode[] {
  return s.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={`${key}-${i}`}>{part.slice(2, -2)}</strong> : part);
}

export function readLegal(name: "privacy" | "terms") {
  const raw = fs.readFileSync(path.join(process.cwd(), "src/content/legal", `${name}.md`), "utf8");
  return { draft: raw.trimStart().startsWith(DRAFT), body: raw.replace(/<!--[\s\S]*?-->/g, "").trim() };
}

export function LegalDoc({ name }: { name: "privacy" | "terms" }) {
  const { draft, body } = readLegal(name);
  const blocks = body.split(/\n\s*\n/);
  const out: React.ReactNode[] = [];
  blocks.forEach((b, i) => {
    const lines = b.split("\n");
    if (b.startsWith("# ")) out.push(<h1 key={i} className="font-display text-[32px] font-bold leading-[38px]">{b.slice(2)}</h1>);
    else if (b.startsWith("## ")) out.push(<h2 key={i} className="mt-4 text-[20px] font-semibold">{b.slice(3)}</h2>);
    else if (lines.every((l) => l.startsWith("- "))) out.push(
      <ul key={i} className="flex list-disc flex-col gap-1 pl-5">{lines.map((l, j) => <li key={j}>{inline(l.slice(2), `${i}-${j}`)}</li>)}</ul>);
    else if (lines.every((l) => l.startsWith("|"))) {
      const rows = lines.filter((l) => !/^\|\s*-/.test(l)).map((l) => l.slice(1, -1).split("|").map((c) => c.trim()));
      out.push(<div key={i} className="overflow-x-auto"><table className="w-full border-collapse text-[14px]">
        <thead><tr>{rows[0].map((c, j) => <th key={j} className="border-b border-line p-2 text-left font-semibold">{c}</th>)}</tr></thead>
        <tbody>{rows.slice(1).map((r, j) => <tr key={j}>{r.map((c, k) => <td key={k} className="border-b border-line p-2 align-top">{inline(c, `${i}-${j}-${k}`)}</td>)}</tr>)}</tbody>
      </table></div>);
    } else out.push(<p key={i}>{inline(b, `${i}`)}</p>);
  });
  return (
    <main className="mx-auto flex max-w-[760px] flex-col gap-4 px-4 py-10 text-[16px] leading-[26px]">
      <Link href="/" aria-label="Home"><Logo /></Link>
      {draft && <div role="note" className="rounded-m border border-danger bg-danger-soft p-3 text-[14px] font-semibold text-danger">
        Draft for legal review. Not yet in force.</div>}
      {out}
      <p className="mt-6 text-[14px] text-muted"><Link className="underline" href="/privacy">Privacy Policy</Link> · <Link className="underline" href="/terms">Terms of Service</Link></p>
    </main>
  );
}
