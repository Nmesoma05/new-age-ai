// Freelancer Growth: shared types, reference data shapes and tool definitions.
export type Country = { code: string; name: string; currency: string; timezone: string; region: string };
export type Convention = { key: string; label: string; document: string; length: string; photo: string;
  personal_details: string; format: string; notes: string };
export type Resource = { name: string; url: string; category: string; regions: string[]; note: string; source_url: string };
export type Reference = {
  stages: { key: string; label: string; guidance: string }[]; work_modes: { key: string; label: string }[];
  countries: Country[]; currencies: string[]; conventions: Convention[]; conventions_note: string;
  resources: { checked_on: string; categories: Record<string, string>; items: Resource[]; note: string };
};

export type Experience = { title: string; organisation?: string; employment_type?: string; period?: string; location?: string;
  description?: string; achievements?: string[] };
export type Education = { qualification: string; institution?: string; period?: string; notes?: string };
export type Skill = { name: string; level?: string | null; years?: string | null; evidence?: string };
export type Service = { name: string; description?: string; deliverables?: string[]; price?: number | null; currency?: string; pricing_model?: string };
export type PortfolioItem = { title: string; url?: string | null; description?: string; role?: string; outcome?: string };
export type Certification = { name: string; issuer?: string; year?: string; url?: string | null };
export type Language = { language: string; level?: string };
export type SkillRead = { skill: string; evidence_level: "shown" | "stated" | "suggested"; evidence_refs?: string[]; note?: string };
export type Assessment = { summary?: string; stage_read?: string; skills?: SkillRead[]; strengths?: string[];
  gaps?: { gap: string; why_it_matters: string; how_to_close: string }[];
  suggested_directions?: { title: string; kind: string; why: string }[]; headline_options?: string[]; edited_by_user?: boolean };
export type Profile = {
  full_name: string | null; headline: string | null; summary: string | null; career_stage: string; country: string | null;
  city: string | null; timezone: string | null; currency: string | null; work_modes: string[]; interests: string[];
  experiences: Experience[]; education: Education[]; skills: Skill[]; services: Service[]; portfolio: PortfolioItem[];
  certifications: Certification[]; languages: Language[]; links: { label: string; url: string }[]; payment_methods: string[];
  availability: { hours_per_week?: number; start?: string; working_hours?: string };
  rates: { hourly?: number; daily?: number; project_minimum?: number; currency?: string; notes?: string };
  targets: { roles?: string[]; client_types?: string[]; markets?: string[]; income_goal_monthly?: number; currency?: string; goals?: string[]; notes?: string };
  assessment: Assessment; assessment_updated_at: string | null; version: number;
};

export type Checks = { eligibility: { status: string; reasons: string[] };
  timezone: { required_window_local: string; overlap_hours: number; on_date: string; your_hours: string } | null;
  risk_signals: { signal: string; explanation: string }[]; deadline_passed: boolean; verified: boolean; pay_note: string | null };
export type Opportunity = { id: string; kind: string; title: string; organisation: string; url: string | null; source: string;
  source_name: string; remote_type: string; eligible_countries: string[]; excluded_countries: string[]; location_note: string;
  timezone_requirement: { tz?: string; start_hour?: number; end_hour?: number }; pay_min: number | null; pay_max: number | null;
  pay_currency: string | null; pay_period: string; deadline: string | null; description: string; status: string;
  verified_at: string | null; verification_note: string; created_at: string; checks: Checks; analysis?: Record<string, unknown> };
export type ApplicationRow = { id: string; opportunity_id: string | null; title: string; organisation: string; url: string | null;
  status: string; applied_on: string | null; next_step: string; next_step_due: string | null; cv_asset_id: string | null;
  letter_asset_id: string | null; contact: string; expected_pay: string; notes: string;
  history: { at: string; status: string; note: string }[]; created_at: string; updated_at: string };
export type InterviewSession = { id: string; application_id: string | null; role_title: string;
  questions: { question: string; type: string; why_asked: string }[];
  answers: { index: number; answer: string; feedback: Record<string, any> | null; feedback_text: string; at: string }[]; // eslint-disable-line @typescript-eslint/no-explicit-any
  status: string; created_at: string };

export const APP_STATUSES = ["preparing", "applied", "interviewing", "offer", "accepted", "rejected", "withdrawn", "no_response"] as const;
export const REMOTE_TYPES = { remote_global: "Remote, worldwide", remote_regional: "Remote, some regions", hybrid: "Hybrid",
  onsite: "On-site", unknown: "Not stated" } as const;
export const OPP_KINDS = { job: "Job", freelance_project: "Freelance project", contract: "Contract", internship: "Internship",
  fellowship: "Fellowship", grant: "Grant", other: "Other" } as const;
export const PAYMENT_OPTIONS = ["Local bank", "Mobile money", "Payoneer", "Wise", "Grey", "Raenest", "PayPal", "Crypto"];
export const STAGE_ICON: Record<string, string> = { beginner: "🌱", experienced_freelancer: "🧰", job_seeker: "🎯", consultant: "🧭" };

export type FlToolKey = "assessment" | "cv" | "proposal" | "interview" | "portfolio" | "brand" | "outreach" | "pricing" | "learning" | "opportunity";
export type Need = "job_text" | "opportunity" | "application" | "target_role" | "market" | "letter_type" | "platforms" | "weeks" | "questions";
export type FlTool = { key: FlToolKey; title: string; blurb: string; button: string; placeholder: string; needs: Need[]; note?: string };

export const FL_TOOLS: FlTool[] = [
  { key: "assessment", title: "Skills assessment", button: "Assess my skills", needs: [],
    blurb: "Your strengths, gaps and where to focus, separating skills you've shown from ones you've listed.",
    placeholder: "Anything to focus on? (optional)" },
  { key: "cv", title: "CV & resume", button: "Build my CV", needs: ["target_role", "market", "job_text", "opportunity"],
    blurb: "Built only from your profile. Paste a job post to tailor it; we'll show which of its keywords you can honestly claim.",
    placeholder: "e.g. Keep it to one page", note: "The job post is used to decide what to emphasise. It never adds experience you don't have." },
  { key: "proposal", title: "Letters & proposals", button: "Write it", needs: ["letter_type", "target_role", "job_text", "opportunity", "application"],
    blurb: "Cover letters, freelance proposals and short pitches. Every claim is checked against your profile.",
    placeholder: "e.g. Mention I can overlap with US mornings" },
  { key: "interview", title: "Interview prep", button: "Prepare me", needs: ["target_role", "questions", "job_text", "application"],
    blurb: "Likely questions, answer outlines and STAR stories from your real experience. Then practise.",
    placeholder: "e.g. It's a first-round call with a recruiter" },
  { key: "portfolio", title: "Portfolio case study", button: "Write case study", needs: [],
    blurb: "Turn a real project into a clear case study. Results and testimonials only if you give them.",
    placeholder: "Which project? Add any results or a client quote you're allowed to share." },
  { key: "brand", title: "Personal brand", button: "Write bios & posts", needs: ["platforms"],
    blurb: "Bios and post drafts that show your expertise honestly. Nothing is posted for you.",
    placeholder: "e.g. I want to be known for fintech onboarding" },
  { key: "outreach", title: "Client outreach", button: "Plan outreach", needs: [],
    blurb: "Who to approach, where to find them, what to research and message drafts. Nothing is sent for you.",
    placeholder: "Name any companies you're thinking of approaching" },
  { key: "pricing", title: "Services & pricing", button: "Package & price", needs: [],
    blurb: "Clear packages with prices labelled by basis: your rates, your income goal, or a starting point to test.",
    placeholder: "e.g. I mostly work with small startups abroad" },
  { key: "learning", title: "Learning plan", button: "Make my plan", needs: ["weeks"],
    blurb: "A week-by-week plan with a portfolio piece each week. Links only from the checked resource list.",
    placeholder: "e.g. I want to move into product design" },
  { key: "opportunity", title: "Opportunity check", button: "Check this opportunity", needs: ["opportunity"],
    blurb: "Compare a saved listing with your profile, eligibility, time zone and red flags.",
    placeholder: "Anything you're unsure about?" },
];
export const flTool = (k: string) => FL_TOOLS.find((t) => t.key === k);
export const ASSET_LABEL: Record<string, string> = { skills_assessment: "Skills assessment", cv: "CV", cover_letter: "Cover letter",
  proposal: "Proposal", interview_prep: "Interview prep", case_study: "Case study", brand_content: "Brand content",
  outreach_plan: "Outreach plan", service_package: "Services & pricing", learning_plan: "Learning plan",
  opportunity_analysis: "Opportunity check" };

export const payText = (o: Opportunity) => !o.pay_currency ? "Pay not stated"
  : `${o.pay_currency} ${o.pay_min?.toLocaleString("en-GB") ?? "?"}${o.pay_max ? "–" + o.pay_max.toLocaleString("en-GB") : ""} / ${o.pay_period}`;
