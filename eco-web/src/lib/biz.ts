// Business Marketing division: shared types, labels and tool definitions.
export const CHANNELS: { id: string; label: string }[] = [
  { id: "whatsapp", label: "WhatsApp" }, { id: "instagram", label: "Instagram" }, { id: "facebook", label: "Facebook" },
  { id: "tiktok", label: "TikTok" }, { id: "x", label: "X" }, { id: "linkedin", label: "LinkedIn" },
  { id: "youtube", label: "YouTube" }, { id: "google_business_profile", label: "Google Business Profile" },
  { id: "website_seo", label: "Website & SEO" }, { id: "google_search_ads", label: "Google Search ads" },
  { id: "meta_ads", label: "Meta ads" }, { id: "email", label: "Email" }, { id: "sms", label: "SMS" },
  { id: "marketplaces", label: "Marketplaces" }, { id: "referrals", label: "Referrals & word of mouth" },
  { id: "events", label: "Events" }, { id: "partnerships", label: "Partnerships" },
  { id: "print_outdoor", label: "Print & outdoor" }, { id: "radio_tv", label: "Radio & TV" },
  { id: "sales_outreach", label: "Sales outreach" }, { id: "other", label: "Other" },
];
export const channelLabel = (c: string) => CHANNELS.find((x) => x.id === c)?.label ?? c;
export const SOCIAL = ["instagram", "facebook", "tiktok", "whatsapp", "x", "linkedin", "youtube", "threads", "pinterest"] as const;

export type Category = { key: string; label: string; examples: string; focus: string; channels: string[]; metrics: string; caution: string };
export type Stage = { key: string; label: string; guidance: string };
export type Offer = { name: string; price?: string | null; description?: string | null };
export type ChannelUse = { channel: string; status: "using" | "tried" | "considering"; notes?: string };
export type Goal = { goal: string; metric?: string; target?: string; due?: string | null };
export type BizCompetitor = { name: string; website?: string | null; notes?: string };
export type Segment = { name: string; description: string; needs: string[]; buying_triggers: string[]; where_to_reach: string[] };
export type Intelligence = {
  summary: string; stage_assessment: string; positioning_statement: string; value_proposition: string;
  customer_segments: Segment[]; competitive_landscape: { competitor: string; what_we_know: string; how_to_stand_out: string }[];
  channel_fit: { channel: string; fit: "strong" | "possible" | "weak"; why: string }[];
  priorities: string[]; risks: string[]; data_gaps: string[]; edited_by_user?: boolean; uncertainties?: string[];
};
export type BusinessProfile = {
  business_name: string; category: string; industry: string; sub_type: string | null; stage: string;
  business_model: "b2c" | "b2b" | "both"; location: string | null; target_markets: string[]; website: string | null;
  offers: Offer[]; customers: string | null; differentiators: string | null; competitors: BizCompetitor[];
  channels: ChannelUse[]; goals: Goal[]; budget: { monthly_amount?: number | null; currency?: string; notes?: string };
  brand: Record<string, any>; intelligence: Partial<Intelligence>; intelligence_updated_at: string | null; version: number;
};
export type BusinessSummary = { workspace_id: string; workspace_name: string; org_id: string; org_name: string; org_kind: string;
  role: string; business_name: string | null; category: string | null; stage: string | null; location: string | null;
  profile_complete: number; has_intelligence: boolean; created_at: string };

export type ChannelTotals = { channel: string; rows: number; spend: number | null; impressions: number | null; clicks: number | null;
  leads: number | null; customers: number | null; revenue: number | null; cost_per_lead: number | null;
  cost_per_customer: number | null; return_on_spend: number | null; lead_to_customer_pct: number | null; click_rate_pct: number | null };
export type ResultsSummary = { start: string; end: string; currency: string | null; rows: number; totals: ChannelTotals;
  by_channel: ChannelTotals[]; sources: Record<string, number>; caveats: string[]; other_currencies: string[] };
export type ResultRow = { id: string; channel: string; campaign_id: string | null; period_start: string; period_end: string;
  currency: string; spend: number | null; impressions: number | null; clicks: number | null; leads: number | null;
  customers: number | null; revenue: number | null; source: string; notes: string; created_at: string };
export type PendingAction = { id: string; kind: string; title: string; payload: Record<string, any>; status: string;
  from_untrusted: boolean; created_at: string; expires_at: string; decided_at: string | null; result: Record<string, any> };
export type Project = { id: string; name: string; description: string | null; status: string; created_at: string };

export type ToolKey = "intelligence" | "positioning" | "market" | "competitors" | "plan" | "content" | "ads" |
  "acquisition" | "retention" | "report";
export type ToolDef = { key: ToolKey; title: string; blurb: string; button: string; placeholder: string;
  needs?: ("dates" | "months" | "platforms")[]; group: "Understand" | "Plan" | "Grow" };

export const TOOLS: ToolDef[] = [
  { key: "intelligence", group: "Understand", title: "Marketing Intelligence Profile", button: "Build my profile",
    blurb: "A plain-language view of your business, customers, competitors and best-fit channels.",
    placeholder: "Anything to focus on? (optional)" },
  { key: "positioning", group: "Understand", title: "Positioning & messaging", button: "Define my positioning",
    blurb: "Positioning statement, value proposition, brand personality, key messages and taglines.",
    placeholder: "e.g. We're moving upmarket and want to sound more premium" },
  { key: "market", group: "Understand", title: "Market & customer research", button: "Analyse my market",
    blurb: "What we can say from your profile and documents, and how to check it with real customers.",
    placeholder: "e.g. Is there demand for weekday office lunches in Awka?" },
  { key: "competitors", group: "Understand", title: "Competitor analysis", button: "Compare competitors",
    blurb: "Compares you with the competitors you've named, using what you've observed.",
    placeholder: "e.g. Focus on price and delivery" },
  { key: "plan", group: "Plan", title: "Marketing plan", button: "Generate plan", needs: ["months"],
    blurb: "Objectives, channel plan, month-by-month timeline, budget split and what to measure.",
    placeholder: "e.g. Get ready for the December party season" },
  { key: "content", group: "Plan", title: "Content & social strategy (AIDA)", button: "Plan content", needs: ["platforms"],
    blurb: "Attention, Interest, Desire, Action: posts for each stage, rhythm and what to count.",
    placeholder: "e.g. Launching our new jollof party pack" },
  { key: "ads", group: "Plan", title: "Advertising & campaigns", button: "Plan ads", needs: ["dates"],
    blurb: "Whether ads make sense now, where, who to target, ad copy and a test plan.",
    placeholder: "e.g. Fill December weekends with party bookings" },
  { key: "acquisition", group: "Grow", title: "Lead generation & acquisition", button: "Build acquisition plan",
    blurb: "Tactics, offers and a simple funnel to bring in new customers or leads.",
    placeholder: "e.g. We want more corporate clients" },
  { key: "retention", group: "Grow", title: "Customer retention", button: "Get retention ideas",
    blurb: "Follow-up, loyalty and win-back ideas that suit how your customers buy.",
    placeholder: "e.g. Customers order once for a party and we never hear from them" },
  { key: "report", group: "Grow", title: "Performance report", button: "Analyse results", needs: ["dates"],
    blurb: "An analysis of the results you've recorded: what worked, what to change.",
    placeholder: "e.g. Which channel should get more budget?" },
];
export const tool = (k: string) => TOOLS.find((t) => t.key === k);

export const money = (v: number | null | undefined, cur?: string | null) =>
  v === null || v === undefined ? "–" : `${cur ? cur + " " : ""}${v.toLocaleString("en-GB", { maximumFractionDigits: 2 })}`;
