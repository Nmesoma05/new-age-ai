// Release gate: production must not ship legal pages that are still drafts (see src/content/legal/*.md).
// Usage: node scripts/check-legal.mjs   -> exit 1 while any file starts with the DRAFT marker.
import fs from "node:fs";
const files = ["privacy", "terms"].map((n) => `src/content/legal/${n}.md`);
const drafts = files.filter((f) => fs.readFileSync(f, "utf8").trimStart().startsWith("<!-- DRAFT"));
// any [placeholder] counts; markdown links [text](url) are fine
const placeholders = files.flatMap((f) => (fs.readFileSync(f, "utf8").match(/\[[^\]\n]+\](?!\()/g) || []).map((m) => `${f}: ${m}`));
if (drafts.length || placeholders.length) {
  console.error(`Legal pages not ready for production:\n${drafts.map((f) => `  ${f}: still marked DRAFT`).join("\n")}`);
  if (placeholders.length) console.error(`  ${placeholders.length} unfilled placeholder(s), e.g.\n    ${placeholders.slice(0, 5).join("\n    ")}`);
  process.exit(1);
}
console.log("Legal pages approved: no draft marker or placeholders.");
