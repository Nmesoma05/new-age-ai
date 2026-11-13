"""Freelancer Growth: reference data and deterministic helpers.

Everything the app can compute exactly (time-zone overlap, eligibility from what a listing states, a minimum rate
from the user's own numbers, scam warning signs) is computed here, not by the model. The AI explains; it doesn't
do the arithmetic or decide eligibility.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models import ProfessionalProfile

# ---------------------------------------------------------------- career stages
STAGES = {
    "beginner": {"label": "Skilled, no clients yet",
                 "guidance": "Build proof before polish: one or two portfolio pieces (practice or pro bono, labelled "
                             "honestly), a narrow starter offer, and steady outreach. Don't overstate experience."},
    "experienced_freelancer": {"label": "Experienced freelancer",
                               "guidance": "Package and price for value, raise rates with evidence, turn past work "
                                           "into case studies, build referrals and repeat clients."},
    "job_seeker": {"label": "Remote job seeker",
                   "guidance": "Target roles that actually hire from the user's country, tailor each CV to the "
                               "posting, track applications and prepare for interviews across time zones."},
    "consultant": {"label": "Independent consultant",
                   "guidance": "Lead with expertise and outcomes, productise offers (audits, retainers), and use "
                               "thought-leadership content and warm outreach to senior buyers."},
}
WORK_MODES = {"freelance": "Freelance projects", "remote_full_time": "Remote full-time", "contract": "Contract",
              "part_time": "Part-time", "internship": "Internship"}

# ---------------------------------------------------------------- countries (ISO 3166-1 alpha-2)
# name, a common local currency, a representative IANA time zone, region. The currency and zone are suggestions
# the user can change (several countries span zones or use more than one currency).
_C = """
DZ|Algeria|DZD|Africa/Algiers|africa
AO|Angola|AOA|Africa/Luanda|africa
BJ|Benin|XOF|Africa/Porto-Novo|africa
BW|Botswana|BWP|Africa/Gaborone|africa
BF|Burkina Faso|XOF|Africa/Ouagadougou|africa
BI|Burundi|BIF|Africa/Bujumbura|africa
CV|Cabo Verde|CVE|Atlantic/Cape_Verde|africa
CM|Cameroon|XAF|Africa/Douala|africa
CF|Central African Republic|XAF|Africa/Bangui|africa
TD|Chad|XAF|Africa/Ndjamena|africa
KM|Comoros|KMF|Indian/Comoro|africa
CG|Congo|XAF|Africa/Brazzaville|africa
CD|DR Congo|CDF|Africa/Kinshasa|africa
CI|Côte d'Ivoire|XOF|Africa/Abidjan|africa
DJ|Djibouti|DJF|Africa/Djibouti|africa
EG|Egypt|EGP|Africa/Cairo|africa
GQ|Equatorial Guinea|XAF|Africa/Malabo|africa
ER|Eritrea|ERN|Africa/Asmara|africa
SZ|Eswatini|SZL|Africa/Mbabane|africa
ET|Ethiopia|ETB|Africa/Addis_Ababa|africa
GA|Gabon|XAF|Africa/Libreville|africa
GM|Gambia|GMD|Africa/Banjul|africa
GH|Ghana|GHS|Africa/Accra|africa
GN|Guinea|GNF|Africa/Conakry|africa
GW|Guinea-Bissau|XOF|Africa/Bissau|africa
KE|Kenya|KES|Africa/Nairobi|africa
LS|Lesotho|LSL|Africa/Maseru|africa
LR|Liberia|LRD|Africa/Monrovia|africa
LY|Libya|LYD|Africa/Tripoli|africa
MG|Madagascar|MGA|Indian/Antananarivo|africa
MW|Malawi|MWK|Africa/Blantyre|africa
ML|Mali|XOF|Africa/Bamako|africa
MR|Mauritania|MRU|Africa/Nouakchott|africa
MU|Mauritius|MUR|Indian/Mauritius|africa
MA|Morocco|MAD|Africa/Casablanca|africa
MZ|Mozambique|MZN|Africa/Maputo|africa
NA|Namibia|NAD|Africa/Windhoek|africa
NE|Niger|XOF|Africa/Niamey|africa
NG|Nigeria|NGN|Africa/Lagos|africa
RW|Rwanda|RWF|Africa/Kigali|africa
ST|São Tomé and Príncipe|STN|Africa/Sao_Tome|africa
SN|Senegal|XOF|Africa/Dakar|africa
SC|Seychelles|SCR|Indian/Mahe|africa
SL|Sierra Leone|SLE|Africa/Freetown|africa
SO|Somalia|SOS|Africa/Mogadishu|africa
ZA|South Africa|ZAR|Africa/Johannesburg|africa
SS|South Sudan|SSP|Africa/Juba|africa
SD|Sudan|SDG|Africa/Khartoum|africa
TZ|Tanzania|TZS|Africa/Dar_es_Salaam|africa
TG|Togo|XOF|Africa/Lome|africa
TN|Tunisia|TND|Africa/Tunis|africa
UG|Uganda|UGX|Africa/Kampala|africa
ZM|Zambia|ZMW|Africa/Lusaka|africa
ZW|Zimbabwe|USD|Africa/Harare|africa
US|United States|USD|America/New_York|north_america
CA|Canada|CAD|America/Toronto|north_america
MX|Mexico|MXN|America/Mexico_City|latin_america
BR|Brazil|BRL|America/Sao_Paulo|latin_america
AR|Argentina|ARS|America/Argentina/Buenos_Aires|latin_america
CO|Colombia|COP|America/Bogota|latin_america
JM|Jamaica|JMD|America/Jamaica|latin_america
GB|United Kingdom|GBP|Europe/London|europe
IE|Ireland|EUR|Europe/Dublin|europe
DE|Germany|EUR|Europe/Berlin|europe
FR|France|EUR|Europe/Paris|europe
NL|Netherlands|EUR|Europe/Amsterdam|europe
BE|Belgium|EUR|Europe/Brussels|europe
ES|Spain|EUR|Europe/Madrid|europe
PT|Portugal|EUR|Europe/Lisbon|europe
IT|Italy|EUR|Europe/Rome|europe
PL|Poland|PLN|Europe/Warsaw|europe
SE|Sweden|SEK|Europe/Stockholm|europe
NO|Norway|NOK|Europe/Oslo|europe
DK|Denmark|DKK|Europe/Copenhagen|europe
CH|Switzerland|CHF|Europe/Zurich|europe
TR|Türkiye|TRY|Europe/Istanbul|europe
AE|United Arab Emirates|AED|Asia/Dubai|middle_east
SA|Saudi Arabia|SAR|Asia/Riyadh|middle_east
QA|Qatar|QAR|Asia/Qatar|middle_east
IN|India|INR|Asia/Kolkata|asia
PK|Pakistan|PKR|Asia/Karachi|asia
BD|Bangladesh|BDT|Asia/Dhaka|asia
PH|Philippines|PHP|Asia/Manila|asia
ID|Indonesia|IDR|Asia/Jakarta|asia
MY|Malaysia|MYR|Asia/Kuala_Lumpur|asia
SG|Singapore|SGD|Asia/Singapore|asia
JP|Japan|JPY|Asia/Tokyo|asia
AU|Australia|AUD|Australia/Sydney|oceania
NZ|New Zealand|NZD|Pacific/Auckland|oceania
"""
COUNTRIES: dict[str, dict] = {}
for _line in _C.strip().splitlines():
    _code, _name, _cur, _tz, _region = _line.split("|")
    COUNTRIES[_code] = {"name": _name, "currency": _cur, "timezone": _tz, "region": _region}

EU = {"IE", "DE", "FR", "NL", "BE", "ES", "PT", "IT", "PL", "SE", "DK"}  # members in this list only
REGIONS = {  # tokens a listing may use instead of country codes
    "WORLDWIDE": None, "ANYWHERE": None,
    "AFRICA": {c for c, v in COUNTRIES.items() if v["region"] == "africa"},
    "EU": EU, "EUROPE": {c for c, v in COUNTRIES.items() if v["region"] == "europe"},
    "EMEA": {c for c, v in COUNTRIES.items() if v["region"] in ("europe", "middle_east", "africa")},
    "AMERICAS": {c for c, v in COUNTRIES.items() if v["region"] in ("north_america", "latin_america")},
    "LATAM": {c for c, v in COUNTRIES.items() if v["region"] == "latin_america"},
    "APAC": {c for c, v in COUNTRIES.items() if v["region"] in ("asia", "oceania")},
    "MIDDLE_EAST": {c for c, v in COUNTRIES.items() if v["region"] == "middle_east"},
}
CURRENCIES = sorted({v["currency"] for v in COUNTRIES.values()} | {"EUR", "USD", "GBP"})


def country_name(code: str | None) -> str:
    return COUNTRIES.get(code or "", {}).get("name", code or "")


# ---------------------------------------------------------------- application conventions
# General, widely described norms. Employers' own instructions always come first; the UI and agents say so.
CONVENTIONS = {
    "global_remote": {"label": "International remote (default)", "document": "CV/resume",
                      "length": "1–2 pages", "photo": "Leave it out", "personal_details":
                      "Name, city and country, time zone, email, phone with country code, LinkedIn/portfolio. "
                      "No date of birth, marital status, religion or ID numbers.",
                      "format": "Plain, single-column layout that applicant-tracking systems can read; PDF unless "
                                "asked otherwise", "notes": "State your time zone and working-hour overlap; say "
                                "whether you work as a contractor."},
    "us": {"label": "United States", "document": "Resume", "length": "1 page early career, up to 2 later",
           "photo": "Leave it out", "personal_details": "No date of birth, photo, marital status or full address",
           "format": "US Letter size; American spelling; month/year dates",
           "notes": "Bullet points that start with action verbs; quantify only what you can stand behind."},
    "canada": {"label": "Canada", "document": "Resume", "length": "1–2 pages", "photo": "Leave it out",
               "personal_details": "No date of birth, photo or marital status", "format": "US Letter size",
               "notes": "Similar to US norms; mention work authorisation only if asked."},
    "uk": {"label": "United Kingdom", "document": "CV", "length": "Usually 2 pages", "photo": "Leave it out",
           "personal_details": "No date of birth or photo", "format": "A4; British spelling",
           "notes": "A short personal profile at the top is common; references 'available on request' is optional."},
    "europe": {"label": "Continental Europe", "document": "CV", "length": "1–2 pages",
               "photo": "Varies by country (more common in e.g. Germany); follow the posting",
               "personal_details": "Some employers expect more detail than UK/US; share only what the posting asks",
               "format": "A4; Europass format is accepted by some employers, rarely required",
               "notes": "List language levels (CEFR, e.g. B2) if you have them."},
    "middle_east": {"label": "Gulf / Middle East", "document": "CV", "length": "2 pages",
                    "photo": "Often included; follow the posting", "personal_details":
                    "Nationality and visa status are often requested; share only what the posting asks",
                    "format": "A4", "notes": "Check visa and relocation terms carefully."},
    "africa_local": {"label": "Local roles in African markets", "document": "CV", "length": "2 pages typical",
                     "photo": "Usually not needed; follow the posting", "personal_details":
                     "Some local postings ask for more personal detail; for international roles, leave it out",
                     "format": "A4", "notes": "NYSC or national service status may be relevant for Nigerian roles."},
}
CONVENTIONS_NOTE = "General conventions only. The employer's or platform's own instructions always come first."


# ---------------------------------------------------------------- eligibility & time zones
@dataclass
class Eligibility:
    status: str          # eligible | not_eligible | unclear
    reasons: list[str]

    def as_dict(self) -> dict:
        return {"status": self.status, "reasons": self.reasons}


def _expand(codes: list[str]) -> tuple[set[str] | None, list[str]]:
    """Listing location tokens -> set of country codes (None = worldwide) and any tokens we didn't recognise."""
    out: set[str] = set()
    unknown = []
    for raw in codes:
        t = raw.strip().upper().replace(" ", "_")
        if t in REGIONS:
            if REGIONS[t] is None:
                return None, unknown
            out |= REGIONS[t]
        elif re.fullmatch(r"[A-Z]{2}", t):
            out.add(t)
        else:
            unknown.append(raw)
    return out, unknown


def eligibility(remote_type: str, eligible: list[str], excluded: list[str], user_country: str | None) -> Eligibility:
    """Only what the listing says. 'unclear' is the honest answer when it says nothing usable."""
    if not user_country:
        return Eligibility("unclear", ["Add your country to your profile to check eligibility."])
    name = country_name(user_country)
    ex, _ = _expand(excluded)
    if ex and user_country in ex:
        return Eligibility("not_eligible", [f"The listing excludes {name}."])
    if remote_type == "onsite":
        return Eligibility("unclear", ["On-site role: check the location and whether relocation or a visa is offered."])
    allowed, unknown = _expand(eligible)
    if allowed is None:
        return Eligibility("eligible", ["The listing says it's open worldwide. Confirm on the original posting."])
    if allowed:
        if user_country in allowed:
            return Eligibility("eligible", [f"{name} is within the locations the listing names. Confirm at the source."])
        return Eligibility("not_eligible", [f"The listing names locations that don't include {name}."] +
                           ([f"Unrecognised location terms: {', '.join(unknown)}"] if unknown else []))
    if remote_type == "remote_global":
        return Eligibility("eligible", ["Marked as global remote. Confirm the hiring countries at the source."])
    return Eligibility("unclear", ["The listing doesn't say which countries can apply. Check the original posting or ask."])


def tz_ok(name: str | None) -> bool:
    if not name:
        return False
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def overlap_hours(user_tz: str, req: dict, on: date | None = None, user_hours: tuple[int, int] = (8, 20)) -> dict | None:
    """Hours of overlap between the role's required window (in its own zone) and the user's waking work window.
    Computed for a specific date so daylight-saving shifts are reflected."""
    if not req or not tz_ok(req.get("tz")) or not tz_ok(user_tz):
        return None
    on = on or date.today()
    rz, uz = ZoneInfo(req["tz"]), ZoneInfo(user_tz)
    rs = datetime.combine(on, time(int(req.get("start_hour", 9)) % 24), rz)
    re_ = rs + timedelta(hours=(int(req.get("end_hour", 17)) - int(req.get("start_hour", 9))) % 24 or 24)
    local_start, local_end = rs.astimezone(uz), re_.astimezone(uz)
    best = 0.0
    for day in (-1, 0, 1):  # user's window on adjacent local days
        d = (local_start + timedelta(days=day)).date()
        us = datetime.combine(d, time(user_hours[0]), uz)
        ue = datetime.combine(d, time(user_hours[1] % 24), uz) if user_hours[1] < 24 else us + timedelta(hours=24 - user_hours[0])
        o = (min(ue, local_end) - max(us, local_start)).total_seconds() / 3600
        best = max(best, o)
    return {"required_window_local": f"{local_start:%H:%M}–{local_end:%H:%M} your time",
            "overlap_hours": round(max(best, 0), 1), "on_date": on.isoformat(),
            "your_hours": f"{user_hours[0]:02d}:00–{user_hours[1] % 24:02d}:00"}


# ---------------------------------------------------------------- pricing floor (the user's own numbers)
def rate_floor(income_goal_monthly: float, hours_per_week: float, monthly_costs: float = 0.0,
               billable_share: float = 0.6, tax_pct: float = 0.0) -> dict:
    """Minimum hourly/daily rate to reach the user's own income goal. Assumptions are returned with the result."""
    if income_goal_monthly <= 0 or hours_per_week <= 0 or not (0 < billable_share <= 1) or not (0 <= tax_pct < 90):
        raise ValueError("income, hours and shares must be positive")
    billable_month = hours_per_week * 52 / 12 * billable_share
    gross = (income_goal_monthly + monthly_costs) / (1 - tax_pct / 100)
    hourly = gross / billable_month
    return {"hourly_floor": round(hourly, 2), "daily_floor": round(hourly * 8, 2),
            "billable_hours_per_month": round(billable_month, 1), "gross_needed_monthly": round(gross, 2),
            "assumptions": {"income_goal_monthly": income_goal_monthly, "hours_per_week": hours_per_week,
                            "monthly_costs": monthly_costs, "billable_share": billable_share, "tax_pct": tax_pct}}


# ---------------------------------------------------------------- scam / risk signals in listings
SCAM_SIGNALS = [
    ("upfront_fee", re.compile(r"\b(registration|application|training|processing|onboarding|starter[- ]kit)\s+fees?\b"
                               r"|\bpay (a|the) (small )?fee\b|\bfee to (apply|start|join)\b", re.I),
     "Asks you to pay to apply or start. Legitimate employers and clients don't charge applicants."),
    ("chat_only", re.compile(r"\b(interview|contact|apply)\b[^.\n]{0,40}\b(telegram|whatsapp|signal)\b"
                             r"|\b(telegram|whatsapp)\b[^.\n]{0,40}\b(only|interview)\b", re.I),
     "Hiring only through a chat app is a common scam pattern. Check the company's real website and domain."),
    ("check_or_equipment", re.compile(r"\b(send|deposit|cash) (you )?a (cheque|check)\b|\bbuy (your )?equipment\b"
                                      r"[^.\n]{0,60}\breimburs", re.I),
     "'We'll send a cheque, you buy equipment' is a known overpayment scam."),
    ("gift_cards_crypto_fees", re.compile(r"\b(gift ?cards?|itunes cards?)\b|\bpay\b[^.\n]{0,30}\b(usdt|bitcoin|crypto)\b"
                                          r"[^.\n]{0,30}\b(fee|deposit)\b", re.I),
     "Requests involving gift cards or paying a deposit in crypto are red flags."),
    ("personal_docs_early", re.compile(r"\b(bvn|bank verification number|bank login|card pin|otp)\b", re.I),
     "Asks for banking credentials or verification codes. Never share these."),
    ("too_good", re.compile(r"\b(no experience needed|no interview)\b[^.\n]{0,80}\b(\$|usd)\s?\d{3,}", re.I),
     "High pay with no experience or interview is unusual. Verify carefully."),
]


def risk_signals(text: str) -> list[dict]:
    return [{"signal": k, "explanation": why} for k, rx, why in SCAM_SIGNALS if rx.search(text or "")]


# ---------------------------------------------------------------- verified resource directory
# Each entry was checked on CHECKED_ON against the source_url given. Availability, fees and supported countries
# change; the UI shows the check date and tells users to confirm for their country before relying on any of them.
CHECKED_ON = "2026-11-12"
_PULSE = "https://www.pulse.ng/story/best-platforms-foreign-remote-jobs-nigeria-2026061013113481896"
_GREY = "https://grey.co/blog/foreign-account-options-for-africans-working-online"
RESOURCES = [
    # remote job boards
    *({"name": n, "url": u, "category": "remote_jobs", "regions": ["global"], "note": note, "source_url": _PULSE}
      for n, u, note in [
          ("We Work Remotely", "https://weworkremotely.com", "Remote-only job board."),
          ("Remote OK", "https://remoteok.com", "Remote job board; many listings show pay."),
          ("Remotive", "https://remotive.com", "Curated remote job board."),
          ("Working Nomads", "https://www.workingnomads.com", "Aggregates remote jobs by category."),
          ("Wellfound", "https://wellfound.com", "Startup jobs (formerly AngelList Talent)."),
          ("Remote.co", "https://remote.co", "Jobs from remote-first companies."),
          ("FlexJobs", "https://www.flexjobs.com", "Paid subscription; listings are screened."),
          ("LinkedIn Jobs", "https://www.linkedin.com/jobs", "Filter by 'Remote' and check each role's location rules."),
      ]),
    {"name": "Remote Africa", "url": "https://remoteafrica.io", "category": "africa_jobs", "regions": ["africa"],
     "note": "Remote roles described as open to African professionals, curated from major remote boards.",
     "source_url": "https://remoteafrica.io/about-us"},
    # freelance marketplaces
    *({"name": n, "url": u, "category": "freelance_marketplaces", "regions": ["global"], "note": note,
       "source_url": _PULSE}
      for n, u, note in [
          ("Upwork", "https://www.upwork.com", "Freelance marketplace: you bid on projects."),
          ("Toptal", "https://www.toptal.com", "Screened network for experienced professionals."),
      ]),
    # getting paid across borders
    *({"name": n, "url": u, "category": "payments", "regions": ["africa", "global"], "note": note, "source_url": src}
      for n, u, note, src in [
          ("Payoneer", "https://www.payoneer.com", "Receive from international clients and platforms; transfers "
           "can take a few days and fees vary.", _GREY),
          ("Wise", "https://wise.com", "Multi-currency transfers; features differ by country.", _GREY),
          ("Grey", "https://grey.co", "Foreign-currency accounts aimed at Africans working online.", _GREY),
          ("Raenest", "https://www.raenest.com", "USD/GBP/EUR accounts for African freelancers and remote workers "
           "(formerly Geegpay).", "https://techcabal.com/2025/11/04/raenest-zero-deposit-fees/"),
          ("Chipper Cash", "https://www.chippercash.com", "Mostly suited to payments within Africa.", _GREY),
      ]),
    # skills
    {"name": "ALX Africa", "url": "https://www.alxafrica.com", "category": "learning", "regions": ["africa"],
     "note": "Tech and AI career programmes for African learners; some are sponsored.",
     "source_url": "https://www.alxafrica.com/frequently-asked-questions"},
]
RESOURCE_URLS = {r["url"] for r in RESOURCES}
RESOURCE_CATEGORIES = {"remote_jobs": "Remote job boards", "africa_jobs": "Africa-focused remote jobs",
                       "freelance_marketplaces": "Freelance marketplaces", "payments": "Getting paid across borders",
                       "learning": "Learning"}


# ---------------------------------------------------------------- profile helpers
def completeness(p: ProfessionalProfile | None) -> int:
    if p is None:
        return 0
    checks = [p.headline, p.summary, p.country, p.timezone, p.currency, p.skills, p.experiences or p.portfolio,
              p.services or (p.targets or {}).get("roles"), p.languages, p.work_modes]
    return round(100 * sum(bool(c) for c in checks) / len(checks))


def missing_basics(p: ProfessionalProfile | None) -> list[str]:
    if p is None:
        return ["your profile"]
    pairs = [("headline", p.headline), ("country", p.country), ("time zone", p.timezone), ("skills", p.skills),
             ("experience or portfolio", p.experiences or p.portfolio), ("currency", p.currency)]
    return [k for k, v in pairs if not v]


def professional_context(p: ProfessionalProfile) -> str:
    """Framing block placed before every tool request. The details themselves are read with get_profile."""
    st = STAGES.get(p.career_stage, STAGES["beginner"])
    c = COUNTRIES.get(p.country or "")
    lines = ["## Professional context (from the user's profile; read details with get_profile)",
             f"Career stage: {st['label']}",
             f"Based in: {', '.join(x for x in (p.city, c['name'] if c else p.country) if x) or 'not set'}",
             f"Time zone: {p.timezone or 'not set'}",
             f"Preferred currency: {p.currency or 'not set'}",
             f"Looking for: {', '.join(WORK_MODES.get(m, m) for m in p.work_modes) or 'not set'}",
             f"Can receive payment via: {', '.join(p.payment_methods) or 'not stated'}",
             "", f"Stage guidance (general; the user's facts win): {st['guidance']}"]
    if c and c["region"] == "africa":
        lines.append("Cross-border notes: consider time-zone overlap with clients, how the user can actually get "
                     "paid from abroad (don't assume any provider works in their country), platform availability and "
                     "fees, and contract/invoice basics. Don't present local norms as universal.")
    return "\n".join(lines)


def next_steps(p: ProfessionalProfile | None, saved: set[str], counts: dict) -> list[dict]:
    """Deterministic dashboard suggestions by career stage and what exists."""
    if p is None:
        return [{"tool": "profile", "title": "Set up your profile", "why": "Every tool works from it."}]
    steps: list[dict] = []
    gaps = missing_basics(p)
    if gaps:
        steps.append({"tool": "profile", "title": "Fill in your profile", "why": "Missing: " + ", ".join(gaps)})
    if not p.assessment:
        steps.append({"tool": "assessment", "title": "Get your skills assessment",
                      "why": "See your strengths, gaps and what to offer first."})
    if counts.get("follow_ups_due"):
        steps.append({"tool": "applications", "title": f"{counts['follow_ups_due']} follow-up(s) due",
                      "why": "Next steps on your applications are due."})
    if counts.get("interviewing"):
        steps.append({"tool": "interview", "title": "Practise for your interview",
                      "why": "You have applications at interview stage."})
    if counts.get("unverified"):
        steps.append({"tool": "opportunities", "title": "Verify saved opportunities",
                      "why": "Check they're real and still open at the source before applying."})
    by_stage = {
        "beginner": [("services", "service_package", "Package a starter offer", "A clear, narrow offer is easier to sell."),
                     ("portfolio", "case_study", "Write your first case study", "Proof matters more than polish."),
                     ("outreach", "outreach_plan", "Plan client outreach", "Find and approach your first clients."),
                     ("brand", "brand_content", "Post about your work", "Make your skills visible.")],
        "experienced_freelancer": [("services", "service_package", "Repackage and price your services", "Price on value, not hours."),
                                   ("portfolio", "case_study", "Turn past projects into case studies", "Win better clients."),
                                   ("outreach", "outreach_plan", "Plan outreach to better-fit clients", "Fill your pipeline.")],
        "job_seeker": [("cv", "cv", "Build a tailored CV", "One CV per role type works better than one for all."),
                       ("opportunities", None, "Add roles you're interested in", "Check eligibility and time zones."),
                       ("interview", "interview_prep", "Prepare for interviews", "Practise answers from your real experience.")],
        "consultant": [("services", "service_package", "Productise your offers", "Audits, sprints and retainers."),
                       ("brand", "brand_content", "Share your expertise", "Thought leadership brings inbound work."),
                       ("outreach", "outreach_plan", "Plan warm outreach", "Reach decision-makers.")],
    }[p.career_stage if p.career_stage in STAGES else "beginner"]
    for tool, asset, title, why in by_stage:
        if (asset is None and not counts.get("opportunities")) or (asset and asset not in saved):
            steps.append({"tool": tool, "title": title, "why": why})
    if "learning_plan" not in saved:
        steps.append({"tool": "learning", "title": "Make a learning plan", "why": "Close the gaps that matter most."})
    return steps[:6]


CAPABILITIES = [
    {"feature": "Professional profile & skills assessment", "status": "operational",
     "detail": "Your profile powers every tool. The assessment separates skills you've shown evidence for from ones "
               "you've only listed, and labels suggestions."},
    {"feature": "CV & resume builder (job-tailored)", "status": "operational",
     "detail": "Built only from your profile; tailored to a pasted job description and a target market's conventions."},
    {"feature": "Proposals, applications & cover letters", "status": "operational",
     "detail": "Every claim cites your profile or your own words. Job posts are never treated as your experience."},
    {"feature": "Interview preparation & mock interviews", "status": "operational",
     "detail": "Likely questions, answer outlines from your real experience, and feedback on typed answers."},
    {"feature": "Portfolio & case studies", "status": "operational",
     "detail": "Results and testimonials appear only if you supply them; otherwise placeholders."},
    {"feature": "Personal branding & content", "status": "operational",
     "detail": "Bios and post drafts. Nothing is posted for you."},
    {"feature": "Client acquisition & outreach preparation", "status": "operational",
     "detail": "Ideal clients, research checklists and message drafts. Nothing is sent for you."},
    {"feature": "Service packaging & pricing guidance", "status": "operational",
     "detail": "Packages labelled by basis (your rates, your income goal, or a suggested starting point to test)."},
    {"feature": "Learning plans", "status": "operational",
     "detail": "Week-by-week plan; resource links only from the checked directory."},
    {"feature": "Application tracker & saved work", "status": "operational",
     "detail": "Statuses, follow-ups, linked CVs/letters, versions and exports."},
    {"feature": "Opportunity checks (eligibility, time zone, red flags)", "status": "manual",
     "detail": "For listings you add. Eligibility comes from what the listing states; you confirm it at the source."},
    {"feature": "Remote job discovery", "status": "manual",
     "detail": "A checked directory of job boards and marketplaces. No live job feed is connected, so the app "
               "never shows listings it hasn't got from you."},
    {"feature": "Live job feeds / auto-apply", "status": "requires_integration",
     "detail": "Not connected. Nothing is submitted for you."},
    {"feature": "Sending outreach or posting content", "status": "requires_integration",
     "detail": "Not connected. You send or post, then track it."},
    {"feature": "Currency conversion", "status": "requires_integration",
     "detail": "No exchange-rate feed. Amounts are shown in their own currency, never converted."},
]
