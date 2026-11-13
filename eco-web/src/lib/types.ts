export type Platform = "instagram" | "x" | "linkedin" | "tiktok" | "facebook" | "youtube" | "threads" | "whatsapp" |
  "pinterest" | "other";
export const PLATFORMS: { id: Platform; label: string; limit?: number }[] = [
  { id: "instagram", label: "Instagram", limit: 2200 }, { id: "x", label: "X", limit: 280 },
  { id: "linkedin", label: "LinkedIn", limit: 3000 }, { id: "tiktok", label: "TikTok", limit: 2200 },
  { id: "facebook", label: "Facebook", limit: 5000 }, { id: "youtube", label: "YouTube", limit: 5000 },
  { id: "threads", label: "Threads", limit: 500 }, { id: "whatsapp", label: "WhatsApp", limit: 1000 },
  { id: "pinterest", label: "Pinterest", limit: 500 },
];
export const platformLabel = (p: string) => PLATFORMS.find((x) => x.id === p)?.label ?? p;

export type ClientSummary = {
  workspace_id: string; workspace_name: string; org_id: string; org_name: string; org_kind: string; role: string;
  client_name: string | null; industry: string | null; platforms: string[]; profile_complete: number; created_at: string;
};
export type Org = { id: string; name: string; kind: string; role: string; plan: string; max_workspaces: number;
  creator_enabled: boolean };
export type OnboardingState = { has_creator_workspace: boolean; orgs: Org[]; clients: ClientSummary[];
  next_step: "create_first_client" | "done" };

export type Offer = { name: string; price?: string | null; description?: string | null };
export type Persona = { name: string; description: string; needs: string[]; where_they_spend_time: string[] };
export type Competitor = { name: string; handle: string; platform: Platform | null; notes: string };
export type Pillar = { name: string; purpose: string; example_topics: string[] };
export type Goal = { goal: string; metric: string; due?: string | null };
export type ClientProfile = {
  client_name: string; contact_email?: string | null; industry: string | null; website: string | null;
  business_info: { description: string; offers: Offer[]; location: string };
  platforms: Platform[]; brand_voice: Record<string, unknown>;
  audience: { summary: string; personas: Persona[]; locations: string[] };
  goals: Goal[]; competitors: Competitor[]; content_pillars: Pillar[]; notes: string | null;
  version?: number; updated_at?: string;
};

export type AssetStatus = "draft" | "in_review" | "approved" | "posted" | "archived";
export type Asset = { id: string; workspace_id: string; type: string; title: string; status: AssetStatus;
  current_version: number; tags: string[]; created_at: string; updated_at: string };
export type AssetVersion = { id: string; version: number; body: Record<string, unknown>; body_text: string;
  source: "ai" | "human"; author_id: string; created_at: string };
export type Comment = { id: string; asset_id: string; asset_version: number; kind: string; body: string; via: string;
  author_user_id: string | null; author_name: string | null; created_at: string };

export type CalendarItem = { id: string; campaign_id: string | null; asset_id: string | null; title: string;
  platform: Platform; format: string; pillar: string | null; notes: string; scheduled_for: string;
  status: "planned" | "drafted" | "ready" | "published_manually" | "skipped"; published_url: string | null;
  published_at: string | null; source: string; asset_title: string | null; asset_status: string | null };

export type Campaign = { id: string; name: string; objective: string; status: string; start_date: string | null;
  end_date: string | null; channels: string[]; budget_note: string; plan: Record<string, any>; source_run_id: string | null;
  created_at: string; updated_at: string; calendar?: CalendarItem[]; counts?: Record<string, number> };

export type RunSummary = { id: string; agent: string; status: string; output: Record<string, any> | null;
  warnings: string[]; uncertainties: string[]; injection_detected: boolean;
  pending_actions: { id: string; kind: string; title: string }[]; saved_asset_id: string | null;
  memory_saved: { id: string; content: string; status: string }[] };
export type Message = { id: string; role: "user" | "assistant"; content: string; created_at: string; asset_id?: string | null };
export type Exchange = { user_message: Message; assistant_message: Message; run: RunSummary };

// null = nobody recorded that figure for any post in the period (shown as –, never as 0)
export type PlatformTotals = { platform: string; posts: number; impressions: number | null; reach: number | null; engagements: number;
  clicks: number | null; video_views: number | null; engagement_rate: number | null };
export type Report = { start: string; end: string; posts: number; totals: PlatformTotals; by_platform: PlatformTotals[];
  top_posts: { label: string; platform: string; published_on: string; url: string | null; impressions: number | null;
    engagements: number }[];
  followers: { platform: string; first: number; first_on: string; last: number; last_on: string; change: number }[];
  sources: Record<string, number>; posts_marked_published: number; caveats: string[] };
export type Metric = { id: string; platform: string; post_label: string; post_url: string | null; published_on: string;
  impressions: number | null; reach: number | null; likes: number | null; comments: number | null; shares: number | null;
  saves: number | null; clicks: number | null; video_views: number | null; source: string; notes: string };

export type Capability = { feature: string; status: "operational" | "manual" | "requires_integration"; detail: string };
export type Page<T> = { data: T[]; next_cursor: string | null };
