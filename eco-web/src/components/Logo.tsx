// New Age AI wordmark (a product of New Age Media). The tile is the app icon: the orange "AI." from the brand logo.
// On light backgrounds "AI." uses the darker text orange so it meets WCAG contrast; on dark it uses the brand orange.
const SUB = {
  creator: { label: "Creator & Marketing", inv: "text-[#A896FF]", ink: "text-d1" },
  business: { label: "Business Marketing", inv: "text-[#5FC79E]", ink: "text-d2" },
  freelancer: { label: "Freelancer Growth", inv: "text-[#6FB6E8]", ink: "text-d3" },
  none: { label: "", inv: "", ink: "" },
} as const;

export function Logo({ inverse = false, division = "none", tagline = false }: {
  inverse?: boolean; division?: keyof typeof SUB; tagline?: boolean }) {
  const s = SUB[division];
  const sub = s.label || (tagline ? "A product of New Age Media" : "");
  return (
    <span className="inline-flex items-center gap-2.5" aria-label={`New Age AI${s.label ? `, ${s.label}` : ""}`} role="img">
      <img src="/icons/icon-192.png" alt="" width={32} height={32} className="h-8 w-8 rounded-[8px]" />
      <span aria-hidden>
        <span className={`block font-display text-[16px] font-bold uppercase leading-4 tracking-[-0.2px] ${inverse ? "text-sidebar-ink" : "text-ink"}`}>
          New Age <span className={inverse ? "text-orange" : "text-orange-text"}>AI.</span>
        </span>
        {sub && <span className={`mt-0.5 block text-[10.5px] font-semibold uppercase tracking-[0.8px] ${
          s.label ? (inverse ? s.inv : s.ink) : inverse ? "text-sidebar-muted" : "text-muted"}`}>{sub}</span>}
      </span>
    </span>
  );
}
