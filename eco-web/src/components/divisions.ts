// Each product division plugs into the same shell: its own nav, product check, list of workspaces and accent.
import {
  BarChart3, BookOpen, Bot, BriefcaseBusiness, CalendarDays, CheckCircle2, ClipboardList, Compass, FileText,
  FolderOpen, GraduationCap, Handshake, LayoutDashboard, Megaphone, MessageSquareText, Mic, Palette, Search, Settings,
  ShieldCheck, Sparkles, Tag, Target, UserRound, type LucideIcon,
} from "lucide-react";

export type NavItem = { href: string; label: string; icon: LucideIcon; short?: string };
export type SwitchRow = { workspace_id: string; label: string; org_name: string; org_kind: string };
export type Division = {
  product: "creator" | "business" | "freelancer";
  name: string;
  root: "/c" | "/b" | "/f";
  listUrl: string;            // API: workspaces of this division the user can open
  allHref: string;            // app: the list page
  allLabel: string;           // "All clients"
  noun: string;               // "client" | "business"
  capabilitiesUrl: string;
  accent: { text: string; soft: string; bg: string };
  switcher?: boolean;         // false when there is only ever one workspace
  nav: { section: string; items: NavItem[] }[];
  mobile: string[];
  rows: (data: any) => SwitchRow[];  // eslint-disable-line @typescript-eslint/no-explicit-any
  agentLabels: Record<string, string>;
  assistant: { intro: string; scope: string; suggestions: string[] };
};

const SHARED_AGENTS = { "shared.document_analyst": "Document analyst", "shared.researcher": "Researcher" };

export const CREATOR: Division = {
  product: "creator", name: "Creator & Marketing", root: "/c", listUrl: "/v1/creator/clients", allHref: "/clients",
  allLabel: "All clients", noun: "client", capabilitiesUrl: "/v1/creator/capabilities",
  accent: { text: "text-d1", soft: "bg-d1-soft", bg: "bg-d1" },
  nav: [
    { section: "Work", items: [
      { href: "", label: "Dashboard", icon: LayoutDashboard }, { href: "/assistant", label: "Assistant", icon: Bot },
      { href: "/studio", label: "Studio", icon: Sparkles }, { href: "/calendar", label: "Calendar", icon: CalendarDays },
      { href: "/campaigns", label: "Campaigns", icon: Megaphone }] },
    { section: "Content", items: [
      { href: "/library", label: "Library", icon: FolderOpen }, { href: "/approvals", label: "Approvals", icon: CheckCircle2 }] },
    { section: "Client", items: [
      { href: "/brand", label: "Brand & audience", icon: Palette }, { href: "/research", label: "Research", icon: Search },
      { href: "/reports", label: "Reports", icon: BarChart3 }, { href: "/settings", label: "Settings", icon: Settings }] },
  ],
  mobile: ["", "/studio", "/calendar", "/library"],
  rows: (list) => list.map((c: any) => ({ workspace_id: c.workspace_id, label: c.client_name || c.workspace_name, org_name: c.org_name, org_kind: c.org_kind })), // eslint-disable-line @typescript-eslint/no-explicit-any
  agentLabels: { "creator.assistant": "Assistant", "creator.content_writer": "Content writer",
    "creator.brand_strategist": "Brand strategist", "creator.calendar_planner": "Calendar planner",
    "creator.campaign_planner": "Campaign planner", "creator.research_analyst": "Research analyst",
    "creator.report_writer": "Report writer", ...SHARED_AGENTS },
  assistant: { intro: "Ask anything about this client's marketing", scope: "Uses this client's profile, memory and documents only",
    suggestions: ["Give me 5 hook ideas for this week", "What should we post more of?", "Summarise the brief I uploaded"] },
};

export const BUSINESS: Division = {
  product: "business", name: "Business Marketing", root: "/b", listUrl: "/v1/business/businesses", allHref: "/businesses",
  allLabel: "All businesses", noun: "business", capabilitiesUrl: "/v1/business/capabilities",
  accent: { text: "text-d2", soft: "bg-d2-soft", bg: "bg-d2" },
  nav: [
    { section: "Plan", items: [
      { href: "", label: "Dashboard", icon: LayoutDashboard }, { href: "/strategist", label: "Strategist", icon: Bot },
      { href: "/tools", label: "Strategy tools", short: "Tools", icon: Sparkles }, { href: "/campaigns", label: "Campaigns", icon: Megaphone }] },
    { section: "Keep", items: [
      { href: "/work", label: "Saved work", short: "Work", icon: FolderOpen }, { href: "/approvals", label: "Approvals", icon: ShieldCheck },
      { href: "/results", label: "Results & reports", short: "Results", icon: BarChart3 }] },
    { section: "Business", items: [
      { href: "/profile", label: "Profile & intelligence", icon: Target }, { href: "/settings", label: "Settings", icon: Settings }] },
  ],
  mobile: ["", "/tools", "/work", "/results"],
  rows: (list) => list.map((b: any) => ({ workspace_id: b.workspace_id, label: b.business_name || b.workspace_name, org_name: b.org_name, org_kind: b.org_kind })), // eslint-disable-line @typescript-eslint/no-explicit-any
  agentLabels: { "business.assistant": "Marketing strategist", "business.aida_strategist": "Content strategist (AIDA)",
    "business.profile_builder": "Profile builder", "business.positioning_strategist": "Positioning strategist",
    "business.market_analyst": "Market analyst", "business.marketing_planner": "Marketing planner",
    "business.ads_planner": "Ads planner", "business.growth_strategist": "Growth strategist",
    "business.performance_analyst": "Performance analyst", ...SHARED_AGENTS },
  assistant: { intro: "Ask your marketing strategist", scope: "Uses this business's profile, saved work and documents only",
    suggestions: ["Where should I spend my first marketing budget?", "How do I get more repeat customers?",
      "What should I ask customers before I run ads?"] },
};

export const FREELANCER: Division = {
  product: "freelancer", name: "Freelancer Growth", root: "/f", listUrl: "/v1/freelancer/onboarding", allHref: "/start",
  allLabel: "All products", noun: "career workspace", capabilitiesUrl: "/v1/freelancer/capabilities", switcher: false,
  accent: { text: "text-d3", soft: "bg-d3-soft", bg: "bg-d3" },
  nav: [
    { section: "Home", items: [
      { href: "", label: "Dashboard", icon: LayoutDashboard }, { href: "/assistant", label: "Career assistant", icon: Bot }] },
    { section: "Get hired", items: [
      { href: "/opportunities", label: "Opportunities", short: "Jobs", icon: Compass },
      { href: "/applications", label: "Applications", short: "Applied", icon: ClipboardList },
      { href: "/tools/cv", label: "CV & resume", icon: FileText },
      { href: "/tools/proposal", label: "Letters & proposals", icon: MessageSquareText },
      { href: "/interview", label: "Interview practice", icon: Mic }] },
    { section: "Win clients", items: [
      { href: "/tools/pricing", label: "Services & pricing", icon: Tag },
      { href: "/tools/outreach", label: "Client outreach", icon: Handshake },
      { href: "/tools/portfolio", label: "Portfolio", icon: BriefcaseBusiness },
      { href: "/tools/brand", label: "Personal brand", icon: Megaphone }] },
    { section: "Grow", items: [
      { href: "/profile", label: "Profile & skills", icon: UserRound },
      { href: "/tools/learning", label: "Learning plan", icon: GraduationCap },
      { href: "/work", label: "Saved work", short: "Saved", icon: FolderOpen },
      { href: "/resources", label: "Resources", icon: BookOpen },
      { href: "/settings", label: "Settings", icon: Settings }] },
  ],
  mobile: ["", "/opportunities", "/applications", "/work"],
  rows: (d) => (d?.workspace_id ? [{ workspace_id: d.workspace_id, label: "My career", org_name: "Personal", org_kind: "personal" }] : []),
  agentLabels: { "freelancer.assistant": "Career assistant", "freelancer.proposal_writer": "Proposal writer",
    "freelancer.skills_assessor": "Skills assessor", "freelancer.cv_writer": "CV writer",
    "freelancer.interview_coach": "Interview coach", "freelancer.answer_coach": "Answer coach",
    "freelancer.portfolio_builder": "Portfolio builder", "freelancer.brand_writer": "Brand writer",
    "freelancer.outreach_planner": "Outreach planner", "freelancer.pricing_advisor": "Pricing advisor",
    "freelancer.learning_planner": "Learning planner", "freelancer.opportunity_analyst": "Opportunity analyst",
    ...SHARED_AGENTS },
  assistant: { intro: "Ask your career assistant", scope: "Uses only your professional profile, saved work and documents",
    suggestions: ["How do I find my first client?", "Should I charge hourly or per project?",
      "How do I explain my time zone to US clients?"] },
};
