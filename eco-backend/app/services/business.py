"""Business Marketing division logic that isn't HTTP.

Category and stage playbooks are short, factual framing for the AI and for the dashboard's next steps, not
templates: they say what typically matters for that kind of business so recommendations start from the right
place. The AI is told they're general guidance and the business's own data wins.
Results maths only uses figures people recorded; nothing here estimates or fetches data.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from app.models import BusinessProfile, MarketingResult

CHANNELS: dict[str, str] = {
    "instagram": "Instagram", "facebook": "Facebook", "tiktok": "TikTok", "x": "X", "linkedin": "LinkedIn",
    "youtube": "YouTube", "whatsapp": "WhatsApp", "google_search_ads": "Google Search ads", "meta_ads": "Meta ads",
    "email": "Email", "sms": "SMS", "website_seo": "Website & SEO", "google_business_profile": "Google Business Profile",
    "marketplaces": "Marketplaces", "referrals": "Referrals", "events": "Events", "partnerships": "Partnerships",
    "print_outdoor": "Print & outdoor", "radio_tv": "Radio & TV", "sales_outreach": "Direct sales & outreach",
    "other": "Other",
}

CATEGORIES: dict[str, dict] = {
    "food_hospitality": {"label": "Food & drink", "examples": "Restaurants, cafés, caterers, bakeries, food vendors",
        "focus": "Local discovery, appetising visuals, reviews and repeat visits; orders often come through WhatsApp, "
                 "delivery apps or walk-ins.",
        "channels": ["instagram", "tiktok", "whatsapp", "google_business_profile", "referrals"],
        "metrics": "orders, bookings, repeat customers, average order value", "caution": "Food safety and allergen claims must be accurate."},
    "retail_ecommerce": {"label": "Retail & e-commerce", "examples": "Shops, online stores, fashion, electronics",
        "focus": "Product discovery, trust (reviews, delivery, returns), conversion and repeat purchase.",
        "channels": ["instagram", "tiktok", "meta_ads", "marketplaces", "email", "whatsapp"],
        "metrics": "sales, conversion rate, cost per order, repeat purchase rate", "caution": "Pricing and delivery promises must be honoured."},
    "beauty_wellness": {"label": "Beauty, fitness & wellness", "examples": "Salons, spas, gyms, skincare, barbers",
        "focus": "Before/after proof, booking convenience, memberships and loyalty.",
        "channels": ["instagram", "tiktok", "whatsapp", "google_business_profile", "referrals"],
        "metrics": "bookings, rebooking rate, membership retention", "caution": "Avoid unproven health or results claims."},
    "professional_services": {"label": "Professional services", "examples": "Law, accounting, consulting, HR, architecture",
        "focus": "Expertise and trust, referrals, thought leadership and a clear enquiry path.",
        "channels": ["linkedin", "website_seo", "referrals", "email", "events", "partnerships"],
        "metrics": "qualified enquiries, consultations booked, proposal win rate", "caution": "Respect professional advertising rules in your jurisdiction."},
    "b2b_tech": {"label": "B2B & technology", "examples": "SaaS, IT services, software, B2B platforms",
        "focus": "Defined buyer roles, demonstrable value, demos/trials, a sales pipeline and content that answers buyer questions.",
        "channels": ["linkedin", "website_seo", "email", "sales_outreach", "google_search_ads", "partnerships", "events"],
        "metrics": "leads, demos, pipeline value, cost per lead, sales cycle length", "caution": "Data-protection rules apply to outreach lists."},
    "health_clinics": {"label": "Healthcare", "examples": "Clinics, pharmacies, dental, diagnostics",
        "focus": "Trust, credentials, access (location, hours, insurance) and patient education.",
        "channels": ["google_business_profile", "website_seo", "whatsapp", "facebook", "referrals"],
        "metrics": "appointments, new patients, recall/return rate", "caution": "Health advertising is regulated; never promise outcomes."},
    "education_training": {"label": "Education & training", "examples": "Schools, tutors, online courses, bootcamps",
        "focus": "Outcomes and testimonials, enrolment cycles, parents or learners as decision makers.",
        "channels": ["facebook", "instagram", "youtube", "whatsapp", "website_seo", "events"],
        "metrics": "enquiries, enrolments, completion and referrals", "caution": "Don't promise grades or job placement you can't evidence."},
    "real_estate_construction": {"label": "Real estate & construction", "examples": "Agents, developers, builders, interiors",
        "focus": "Long decision cycles, high trust, visual proof of projects, lead nurturing.",
        "channels": ["instagram", "facebook", "website_seo", "whatsapp", "referrals", "meta_ads"],
        "metrics": "qualified leads, viewings, deals closed, cost per lead", "caution": "Property claims and prices must be accurate and current."},
    "travel_events": {"label": "Travel, hospitality & events", "examples": "Hotels, tours, event venues, planners",
        "focus": "Seasonality, inspiration, reviews and easy booking.",
        "channels": ["instagram", "tiktok", "google_business_profile", "marketplaces", "email", "partnerships"],
        "metrics": "bookings, occupancy, direct vs. platform bookings", "caution": "Show real photos; disclose fees."},
    "manufacturing_wholesale": {"label": "Manufacturing & wholesale", "examples": "Factories, distributors, FMCG suppliers",
        "focus": "Distributor and retailer relationships, reliability, catalogues and trade relationships.",
        "channels": ["linkedin", "sales_outreach", "events", "whatsapp", "partnerships", "website_seo"],
        "metrics": "new accounts, order volume, reorder rate", "caution": "Specs and certifications must be verifiable."},
    "home_local_services": {"label": "Home & local services", "examples": "Cleaning, repairs, logistics, dispatch, laundry",
        "focus": "Being found when needed, fast response, trust signals and repeat or contract customers.",
        "channels": ["google_business_profile", "whatsapp", "facebook", "referrals", "print_outdoor"],
        "metrics": "jobs booked, response time, repeat customers", "caution": "Be clear about service areas and pricing."},
    "creative_media": {"label": "Creative & media", "examples": "Studios, agencies, photographers, publishers",
        "focus": "Portfolio, niche positioning, referrals and partnerships.",
        "channels": ["instagram", "linkedin", "youtube", "referrals", "partnerships"],
        "metrics": "enquiries, projects won, average project value", "caution": "Only show work you have rights to share."},
    "finance_fintech": {"label": "Finance & fintech", "examples": "Microfinance, insurance, payments, investment",
        "focus": "Trust, security, clear terms and education.",
        "channels": ["website_seo", "linkedin", "facebook", "email", "partnerships"],
        "metrics": "sign-ups, activation, cost per acquisition", "caution": "Financial promotions are regulated; avoid return promises."},
    "agriculture": {"label": "Agriculture & agribusiness", "examples": "Farms, processors, input suppliers, aggregators",
        "focus": "Buyer relationships, reliability of supply, quality proof and seasonality.",
        "channels": ["whatsapp", "sales_outreach", "events", "partnerships", "facebook", "marketplaces"],
        "metrics": "buyers, order volume, repeat contracts", "caution": "Quality and origin claims must be verifiable."},
    "nonprofit": {"label": "Non-profit & community", "examples": "NGOs, charities, faith and community groups",
        "focus": "Impact stories, donor and volunteer journeys, partnerships and transparency.",
        "channels": ["facebook", "instagram", "email", "events", "partnerships", "whatsapp"],
        "metrics": "donors, donations, volunteers, beneficiaries reached", "caution": "Respect beneficiaries' privacy and consent."},
    "other": {"label": "Something else", "examples": "Any other kind of business",
        "focus": "Start from the business's own customers and how they buy today.",
        "channels": [], "metrics": "the outcome that matters most to this business", "caution": ""},
}

STAGES: dict[str, dict] = {
    "idea": {"label": "Idea / pre-launch", "guidance": "Validate demand before spending: talk to potential customers, "
             "test offers cheaply, build a waitlist. Avoid big paid campaigns."},
    "new": {"label": "New (first customers)", "guidance": "Win and delight first customers, collect proof (reviews, "
            "testimonials), lean on referrals and low-cost local channels; spend small and learn."},
    "growing": {"label": "Growing", "guidance": "Find the one or two channels that reliably bring customers, measure "
                "cost per customer, and double down; start retention basics."},
    "established": {"label": "Established", "guidance": "Protect and grow the brand, improve retention and lifetime "
                    "value, test new markets or offers, and make spend more efficient."},
}


def _cur(p: BusinessProfile) -> str:
    return (p.budget or {}).get("currency") or ""


def _amount(v) -> str:
    try:
        return f"{Decimal(str(v)).normalize():,f}"
    except (InvalidOperation, ValueError):
        return str(v)


def business_context(p: BusinessProfile) -> str:
    """Framing added to every Business tool request. General guidance only; the profile's own facts win."""
    cat = CATEGORIES.get(p.category, CATEGORIES["other"])
    st = STAGES.get(p.stage, STAGES["growing"])
    budget = p.budget or {}
    lines = [
        "## Business context (from the profile)",
        f"Category: {cat['label']} ({p.industry}{', ' + p.sub_type if p.sub_type else ''}); model: {p.business_model.upper()}",
        f"Stage: {st['label']}",
        f"Location: {p.location or 'not given'}; target markets: {', '.join(p.target_markets) or 'not given'}",
        "Budget: " + (f"{_amount(budget.get('monthly_amount'))} {budget.get('currency', '')} per month".strip()
                      if budget.get("monthly_amount") not in (None, "") else "not given")
        + (f" ({budget['notes']})" if budget.get("notes") else ""),
        f"Channels in use: {', '.join(CHANNELS.get(c.get('channel'), c.get('channel', '')) + ' (' + c.get('status', 'using') + ')' for c in p.channels) or 'none recorded'}",
        "## General guidance for this kind of business (use it only where it fits the facts above)",
        f"Typical focus: {cat['focus']}",
        f"Often-useful channels: {', '.join(CHANNELS[c] for c in cat['channels']) or 'depends on the business'}",
        f"Useful measures: {cat['metrics']}",
        f"At this stage: {st['guidance']}",
    ]
    if cat["caution"]:
        lines.append(f"Watch out: {cat['caution']}")
    lines.append("Use the local currency and the markets above. If something important is missing, say what in "
                 "uncertainties instead of assuming.")
    return "\n".join(lines)


def completeness(p: BusinessProfile | None) -> int:
    if p is None:
        return 0
    checks = [p.business_name, p.category != "other", p.location or p.target_markets, p.offers, p.customers,
              p.differentiators, p.competitors, p.channels, p.goals, (p.budget or {}).get("monthly_amount") not in (None, "")]
    return round(100 * sum(bool(c) for c in checks) / len(checks))


def next_steps(p: BusinessProfile | None, saved_types: set[str], has_results: bool) -> list[dict]:
    """Deterministic, stage- and category-aware suggestions for the dashboard."""
    if p is None:
        return [{"tool": "profile", "title": "Set up your business profile", "why": "Everything else builds on it."}]
    steps: list[dict] = []
    if not p.intelligence:
        steps.append({"tool": "intelligence", "title": "Create your Marketing Intelligence Profile",
                      "why": "A plain-language summary of your market, customers and best-fit channels."})
    if completeness(p) < 70:
        steps.append({"tool": "profile", "title": "Fill in the gaps in your profile",
                      "why": "Recommendations get more specific with your competitors, channels and budget."})
    if p.stage == "idea" and "research" not in saved_types:
        steps.append({"tool": "market", "title": "Check demand before you spend",
                      "why": "At the idea stage, learning who will buy matters more than reach."})
    if "positioning" not in saved_types and not p.brand:
        steps.append({"tool": "positioning", "title": "Sharpen your positioning and message",
                      "why": "One clear reason to choose you makes every channel work harder."})
    if "marketing_plan" not in saved_types:
        steps.append({"tool": "plan", "title": "Generate a 90-day marketing plan", "why": "Turn goals into a schedule."})
    if p.business_model in ("b2b", "both") or p.category in ("b2b_tech", "professional_services", "manufacturing_wholesale"):
        if "growth_plan" not in saved_types:
            steps.append({"tool": "acquisition", "title": "Build a lead generation plan",
                          "why": "B2B buyers need a steady pipeline, not just visibility."})
    elif "content_plan" not in saved_types:
        steps.append({"tool": "content", "title": "Plan a month of social content (AIDA)",
                      "why": "Customers in your category often discover businesses on social media."})
    if p.stage in ("growing", "established") and "growth_plan" not in saved_types:
        steps.append({"tool": "retention", "title": "Get more from existing customers",
                      "why": "Keeping customers is usually cheaper than finding new ones."})
    if not has_results:
        steps.append({"tool": "results", "title": "Record your marketing results",
                      "why": "Track spend, leads and sales so you know what's working."})
    return steps[:5]


CAPABILITIES: list[dict] = [
    {"feature": "AI marketing strategist (chat)", "status": "operational", "detail": "Answers using your profile, saved work and uploaded documents."},
    {"feature": "Marketing Intelligence Profile", "status": "operational", "detail": "Generated from onboarding answers; every section editable."},
    {"feature": "Positioning, brand identity & messaging", "status": "operational", "detail": "Positioning, value proposition, messages, tone; applied to your profile when you choose."},
    {"feature": "Marketing plan generator", "status": "operational", "detail": "Objectives, channel plan, timeline, budget split and KPIs for your stage and category."},
    {"feature": "Content & social media strategy (AIDA)", "status": "operational", "detail": "Attention, Interest, Desire, Action plan with draft posts per platform."},
    {"feature": "Advertising & campaign planning", "status": "operational", "detail": "Platform choice, targeting ideas, ad copy, test plan; becomes a campaign you can track."},
    {"feature": "Lead generation & acquisition strategy", "status": "operational", "detail": "Tactics, offers, funnel stages and how to measure them."},
    {"feature": "Customer retention ideas", "status": "operational", "detail": "Loyalty, follow-up and win-back ideas suited to how your customers buy."},
    {"feature": "Projects & saved work", "status": "operational", "detail": "Save any output to a project, edit it, keep versions, export it."},
    {"feature": "Market & customer research", "status": "manual", "detail": "Uses your profile, notes and uploaded documents. Live market data and web research need a research provider (not connected)."},
    {"feature": "Competitor analysis", "status": "manual", "detail": "Analyses competitors you name and what you've observed; it can't look at their accounts or ads for you."},
    {"feature": "Performance analysis & reports", "status": "manual", "detail": "Calculated from results you enter or upload (spend, leads, customers, revenue)."},
    {"feature": "Launching ads / spending budget", "status": "requires_integration", "detail": "You can request approval to spend; nothing is launched or paid because no ad account is connected."},
    {"feature": "Sending emails / SMS / WhatsApp broadcasts", "status": "requires_integration", "detail": "Messages can be drafted and proposed for approval; none are sent without a messaging integration."},
    {"feature": "Automatic results import (ads, CRM, analytics, sales)", "status": "requires_integration", "detail": "No ad platform, CRM, analytics or point-of-sale system is connected."},
]


# ---------------------------------------------------------------- results maths
METRICS = ("spend", "impressions", "clicks", "leads", "customers", "revenue")


@dataclass
class ChannelTotals:
    channel: str
    rows: int = 0
    spend: Decimal = Decimal(0)
    impressions: int = 0
    clicks: int = 0
    leads: int = 0
    customers: int = 0
    revenue: Decimal = Decimal(0)
    recorded: set = field(default_factory=set)

    def ratios(self) -> dict:
        def div(a, b, q="0.01"):
            return float((Decimal(a) / Decimal(b)).quantize(Decimal(q))) if b and a is not None else None
        r = self.recorded
        return {
            "cost_per_lead": div(self.spend, self.leads) if {"spend", "leads"} <= r else None,
            "cost_per_customer": div(self.spend, self.customers) if {"spend", "customers"} <= r else None,
            "return_on_spend": div(self.revenue, self.spend) if {"revenue", "spend"} <= r else None,
            "lead_to_customer_pct": div(100 * self.customers, self.leads, "0.1") if {"customers", "leads"} <= r else None,
            "click_rate_pct": div(100 * self.clicks, self.impressions, "0.01") if {"clicks", "impressions"} <= r else None,
        }

    def as_dict(self) -> dict:
        d = {"channel": self.channel, "rows": self.rows}
        for m in METRICS:
            v = getattr(self, m)
            d[m] = (float(v) if isinstance(v, Decimal) else v) if m in self.recorded else None
        return {**d, **self.ratios()}


def summarise_results(start: date, end: date, rows: list[MarketingResult], main_currency: str | None) -> dict:
    by_cur: dict[str, list[MarketingResult]] = {}
    for r in rows:
        by_cur.setdefault(r.currency, []).append(r)
    currency = main_currency if main_currency in by_cur else (max(by_cur, key=lambda c: len(by_cur[c])) if by_cur else main_currency)
    use = by_cur.get(currency, [])
    total, per = ChannelTotals("all"), {}
    sources: dict[str, int] = {}
    for r in use:
        sources[r.source] = sources.get(r.source, 0) + 1
        for t in (total, per.setdefault(r.channel, ChannelTotals(r.channel))):
            t.rows += 1
            for m in METRICS:
                v = getattr(r, m)
                if v is not None:
                    t.recorded.add(m)
                    setattr(t, m, getattr(t, m) + v)
    caveats = []
    if not use:
        caveats.append("No results were recorded for this period.")
    else:
        caveats.append("Figures were entered by your team (by hand or CSV) and haven't been checked against ad "
                       "accounts, analytics or sales systems.")
    others = sorted(c for c in by_cur if c != currency)
    if others:
        caveats.append(f"Rows in {', '.join(others)} are left out of these totals; money in different currencies isn't added together.")
    missing = [m for m in METRICS if use and m not in total.recorded]
    if missing:
        caveats.append("Not recorded for any row: " + ", ".join(missing) + ". Related ratios can't be calculated.")
    overlap = [r for r in use if r.period_start < start or r.period_end > end]
    if overlap:
        caveats.append(f"{len(overlap)} row(s) cover dates partly outside this period and are counted in full.")
    return {"start": start.isoformat(), "end": end.isoformat(), "currency": currency, "rows": len(use),
            "totals": total.as_dict(), "by_channel": sorted((t.as_dict() for t in per.values()),
                                                            key=lambda d: -(d["spend"] or 0)),
            "sources": sources, "caveats": caveats, "other_currencies": others}


def _fmt(v, cur=""):
    if v is None:
        return "not recorded"
    if isinstance(v, float) and not v.is_integer():
        return f"{cur + ' ' if cur else ''}{v:,.2f}"
    return f"{cur + ' ' if cur else ''}{int(v):,}"


def results_text(s: dict) -> str:
    t, cur = s["totals"], s["currency"] or ""
    lines = [f"Marketing results for {s['start']} to {s['end']} (calculated by the system from rows the team recorded; "
             f"{s['rows']} row(s); currency {cur or 'n/a'}):",
             f"Spend: {_fmt(t['spend'], cur)}", f"Leads: {_fmt(t['leads'])}", f"Customers: {_fmt(t['customers'])}",
             f"Revenue: {_fmt(t['revenue'], cur)}", f"Cost per lead: {_fmt(t['cost_per_lead'], cur)}",
             f"Cost per customer: {_fmt(t['cost_per_customer'], cur)}",
             f"Return on spend (revenue / spend): {t['return_on_spend'] if t['return_on_spend'] is not None else 'not recorded'}",
             f"Lead to customer: {t['lead_to_customer_pct'] if t['lead_to_customer_pct'] is not None else 'not recorded'}%"]
    for c in s["by_channel"]:
        lines.append(f"- {CHANNELS.get(c['channel'], c['channel'])}: spend {_fmt(c['spend'], cur)}, leads {_fmt(c['leads'])}, "
                     f"customers {_fmt(c['customers'])}, revenue {_fmt(c['revenue'], cur)}, cost per lead "
                     f"{_fmt(c['cost_per_lead'], cur)}, return on spend {c['return_on_spend'] if c['return_on_spend'] is not None else 'not recorded'}")
    lines += [f"Caveat: {c}" for c in s["caveats"]]
    return "\n".join(lines)


def results_markdown(name: str, s: dict, narrative: str | None) -> str:
    t, cur = s["totals"], s["currency"] or ""
    out = [f"# Marketing results: {name}", f"{s['start']} to {s['end']} · {cur}", "",
           "> Figures were recorded by your team. They were not fetched from ad accounts, analytics or sales systems.", "",
           "## Totals", "| Spend | Leads | Customers | Revenue | Cost per lead | Cost per customer | Return on spend |",
           "|---|---|---|---|---|---|---|",
           f"| {_fmt(t['spend'])} | {_fmt(t['leads'])} | {_fmt(t['customers'])} | {_fmt(t['revenue'])} | "
           f"{_fmt(t['cost_per_lead'])} | {_fmt(t['cost_per_customer'])} | {t['return_on_spend'] if t['return_on_spend'] is not None else 'not recorded'} |"]
    if s["by_channel"]:
        out += ["", "## By channel", "| Channel | Spend | Leads | Customers | Revenue | Cost per lead | Return on spend |",
                "|---|---|---|---|---|---|---|"]
        out += [f"| {CHANNELS.get(c['channel'], c['channel'])} | {_fmt(c['spend'])} | {_fmt(c['leads'])} | {_fmt(c['customers'])} | "
                f"{_fmt(c['revenue'])} | {_fmt(c['cost_per_lead'])} | {c['return_on_spend'] if c['return_on_spend'] is not None else 'not recorded'} |"
                for c in s["by_channel"]]
    if narrative:
        out += ["", "## Analysis (AI-written from the figures above)", narrative]
    out += ["", "## About this data", *(f"- {c}" for c in s["caveats"])]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- CSV import
ALIASES = {"start": "period_start", "from": "period_start", "date": "period_start", "end": "period_end", "to": "period_end",
           "cost": "spend", "amount_spent": "spend", "sales": "customers", "conversions": "customers",
           "orders": "customers", "income": "revenue"}


def parse_results_csv(data: bytes, default_currency: str | None) -> tuple[list[dict], list[dict]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], [{"row": 0, "message": "The file isn't UTF-8 text. Export it as CSV (UTF-8)."}]
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], [{"row": 0, "message": "The file has no header row."}]
    norm = {}
    for h in reader.fieldnames:
        k = re.sub(r"[^a-z_]", "", h.strip().lower().replace(" ", "_"))
        norm[h] = ALIASES.get(k, k)
    need = [c for c in ("channel", "period_start") if c not in norm.values()]
    if "currency" not in norm.values() and not default_currency:
        need.append("currency")
    if need:
        return [], [{"row": 1, "message": "Missing column(s): " + ", ".join(need)}]
    rows, errors = [], []
    for i, raw in enumerate(reader, start=2):
        if i > 2001:
            errors.append({"row": i, "message": "Too many rows; the limit is 2000."})
            break
        r = {norm[k]: (v or "").strip() for k, v in raw.items() if k in norm}
        if not any(r.values()):
            continue
        ch = r.get("channel", "").lower().replace(" ", "_").replace("&", "and")
        ch = {"google_ads": "google_search_ads", "facebook_ads": "meta_ads", "instagram_ads": "meta_ads",
              "seo": "website_seo", "website": "website_seo", "twitter": "x"}.get(ch, ch)
        if ch not in CHANNELS:
            errors.append({"row": i, "message": f"Unknown channel {r.get('channel')!r}."})
            continue
        try:
            ps = date.fromisoformat(r.get("period_start", "")[:10])
            pe = date.fromisoformat((r.get("period_end") or r.get("period_start", ""))[:10])
        except ValueError:
            errors.append({"row": i, "message": "Dates must look like 2026-11-30."})
            continue
        if pe < ps:
            errors.append({"row": i, "message": "period_end is before period_start."})
            continue
        cur = (r.get("currency") or default_currency or "").upper()
        if not re.fullmatch(r"[A-Z]{3}", cur):
            errors.append({"row": i, "message": "currency must be a 3-letter code like NGN."})
            continue
        vals, bad = {}, None
        for m in METRICS:
            v = r.get(m, "").replace(",", "")
            if v == "":
                vals[m] = None
                continue
            try:
                n = Decimal(v) if m in ("spend", "revenue") else int(v)
                if n < 0:
                    raise ValueError
                vals[m] = n
            except (InvalidOperation, ValueError):
                bad = m
                break
        if bad:
            errors.append({"row": i, "message": f"{bad} must be a non-negative number (or empty)."})
            continue
        rows.append({"channel": ch, "period_start": ps, "period_end": pe, "currency": cur, **vals})
    return rows, errors
