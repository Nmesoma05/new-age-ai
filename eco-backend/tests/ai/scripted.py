"""ScriptedProvider: replaces only the external LLM. It records every request (so tests can assert exactly what
a model would have seen) and replays scripted responses per agent. Scripts can play a well-behaved model or a
compromised one (e.g. one that obeys an injected instruction) so tests can check the code stops it."""
from __future__ import annotations

import copy
import json
import re
from collections import defaultdict, deque

from app.ai.providers.base import LLMRequest, LLMResponse, ProviderError, ToolCall

_n = 0


def final(obj: dict, tokens=(100, 50)) -> LLMResponse:
    return LLMResponse(text=json.dumps(obj), tool_calls=[], stop="end", model="scripted", tokens_in=tokens[0],
                       tokens_out=tokens[1], latency_ms=5)


def call(name: str, args: dict | None, *more: tuple[str, dict]) -> LLMResponse:
    global _n
    calls = []
    for nm, a in ((name, args), *more):
        _n += 1
        calls.append(ToolCall(f"call_{_n}", nm, a, json.dumps(a) if a is not None else "{oops"))
    return LLMResponse(text="", tool_calls=calls, stop="tool_calls", model="scripted", tokens_in=80, tokens_out=20,
                       latency_ms=5)


def user_request(req: LLMRequest) -> str:
    """The user's request from the task message (also on repair rounds, where the last message is the repair note)."""
    users = [m.content for m in req.messages if m.role == "user" and m.content]
    for c in users:
        m = re.search(r"## User request\n(.*)\Z", c, re.S)
        if m:
            return m.group(1).strip()
    return users[-1].strip()


def everything_sent(req: LLMRequest) -> str:
    return req.system + "\n" + "\n".join((m.content or "") + json.dumps([c.arguments for c in m.tool_calls])
                                         for m in req.messages)


class ScriptedProvider:
    name = "scripted"

    def __init__(self, default: bool = True):
        self.queues: dict[str, deque] = defaultdict(deque)
        self.requests: list[LLMRequest] = []
        self.default = default
        self.fail: str | None = None

    def model_for(self, tier):
        return f"scripted-{tier}"

    def on(self, agent: str, *steps) -> "ScriptedProvider":
        self.queues[agent].extend(steps)
        return self

    def sent_to(self, agent: str) -> list[LLMRequest]:
        return [r for r in self.requests if r.metadata.get("agent") == agent]

    async def generate(self, req: LLMRequest) -> LLMResponse:
        self.requests.append(copy.deepcopy(req))
        if self.fail:
            raise ProviderError(self.fail)
        agent = req.metadata["agent"]
        q = self.queues[agent]
        if q:
            step = q.popleft()
            return step(req) if callable(step) else step
        if not self.default:
            raise AssertionError(f"no scripted response for {agent}")
        return self._default(agent, req)

    def _default(self, agent: str, req: LLMRequest) -> LLMResponse:
        if agent == "router":
            product = re.search(r"\b(creator|business|freelancer)\.assistant\b", req.messages[-1].content).group(1)
            return final({"agent": f"{product}.assistant", "task_summary": "chat", "belongs_to": "this_workspace",
                          "document_ids": [], "needs_research": False, "user_requested_save": False,
                          "explicit_memory_request": False, "confidence": 0.9, "clarifying_question": None,
                          "unsupported_reason": None}, tokens=(200, 30))
        if agent.endswith(".assistant"):
            return final({"reply": f"Draft reply to: {user_request(req)}", "follow_ups": [], "uncertainties": [],
                          "warnings": [], "memory_candidates": []}, tokens=(1000, 500))
        if agent == "shared.summarizer":
            return final({"summary": "Earlier: discussed ideas.", "open_items": []})
        if agent in CREATOR_DEFAULTS:
            return final(CREATOR_DEFAULTS[agent](user_request(req)), tokens=(900, 400))
        if agent in BUSINESS_DEFAULTS:
            return final(BUSINESS_DEFAULTS[agent](user_request(req)), tokens=(900, 400))
        if agent in FREELANCER_DEFAULTS:
            # behave like a careful model: read the profile first, then cite only refs it returned
            seen = [m for m in req.messages if m.role == "tool" and m.tool_name == "get_profile"]
            if not seen:
                return call("get_profile", {})
            refs = dict(re.findall(r"^\[(profile:.+?)\] (.*)$", seen[-1].content or "", re.M))
            return final(FREELANCER_DEFAULTS[agent](user_request(req), refs), tokens=(900, 400))
        raise AssertionError(f"no default for {agent}")


# ---------------------------------------------------------------- deterministic, validator-passing creator outputs
def _platforms(msg: str, default=("instagram",)) -> list[str]:
    m = re.search(r"^Platforms:\s*(.+)$", msg, re.M)
    return [p.strip() for p in m.group(1).split(",")] if m else list(default)


def _range(msg: str):
    from datetime import date
    m = re.search(r"Date range: (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})", msg)
    return (date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))) if m else None


def _content(msg):
    m = re.search(r"Number of drafts: (\d+)", msg)
    n = int(m.group(1)) if m else 2
    plats = _platforms(msg)
    return {"brief": "Drafts for the brief", "drafts": [
        {"platform": plats[i % len(plats)], "format": "post", "hook": f"Hook idea {chr(65 + i)}",
         "body": f"Draft {chr(65 + i)}: a warm, short post about the brief.", "thread_parts": [],
         "hashtags": ["Brand"], "call_to_action": "Tell us what you think", "visual_idea": "A bright product photo"}
        for i in range(n)], "uncertainties": ["Posting times weren't given."], "warnings": [], "memory_candidates": []}


def _brand(msg):
    return {"positioning": "A friendly brand for people who value quality.",
            "voice_attributes": [{"trait": "Warm", "what_it_means": "Friendly and personal", "avoid": "Cold"},
                                 {"trait": "Clear", "what_it_means": "Plain words", "avoid": "Jargon"}],
            "tone_by_platform": [{"platform": "instagram", "guidance": "Visual and upbeat"}],
            "words_to_use": ["fresh", "together"], "words_to_avoid": ["cheap"],
            "sample_lines": ["Made with care, for you.", "Come as you are."],
            "audience_personas": [{"name": "Busy professional", "description": "Wants quality without fuss",
                                   "needs": ["speed"], "where_they_spend_time": ["instagram"]}],
            "content_pillars": [{"name": "Craft", "purpose": "How it's made", "example_topics": ["process"]},
                                {"name": "Community", "purpose": "People behind it", "example_topics": ["team"]}],
            "uncertainties": [], "warnings": [], "memory_candidates": []}


def _calendar(msg):
    from datetime import timedelta
    start, end = _range(msg)
    plats, items, d, i = _platforms(msg), [], start, 0
    while d <= end and len(items) < 10:
        items.append({"date": d.isoformat(), "time": "09:00", "platform": plats[i % len(plats)], "format": "post",
                      "pillar": "Craft" if i % 2 == 0 else "Community", "title": f"Slot {i + 1}",
                      "idea": "Show the people and process behind the brand"})
        d += timedelta(days=2)
        i += 1
    return {"strategy_summary": "Alternate craft and community posts.", "start_date": start.isoformat(),
            "end_date": end.isoformat(), "posting_rhythm": "Every other day", "items": items,
            "uncertainties": ["Best posting times are unknown."], "warnings": [], "memory_candidates": []}


def _campaign(msg):
    start, end = _range(msg)
    plats = _platforms(msg)
    mid = start + (end - start) / 2
    return {"name": "Launch campaign", "objective": "Introduce the new product", "audience": "Existing followers",
            "key_message": "Something new, made with care.", "start_date": start.isoformat(), "end_date": end.isoformat(),
            "channels": plats, "phases": [
                {"name": "Tease", "start_date": start.isoformat(), "end_date": mid.isoformat(), "goal": "Build curiosity",
                 "activities": ["Countdown"], "deliverables": [{"platform": plats[0], "format": "story",
                                                               "description": "Countdown stories"}]},
                {"name": "Launch", "start_date": mid.isoformat(), "end_date": end.isoformat(), "goal": "Drive trial",
                 "activities": ["Launch post"], "deliverables": [{"platform": plats[0], "format": "post",
                                                                 "description": "Launch announcement"}]}],
            "kpis": [{"metric": "Orders mentioning the launch", "how_to_measure": "Ask at checkout"}],
            "budget_note": "[YOUR BUDGET] if you boost the launch post", "risks": [], "uncertainties": [],
            "warnings": [], "memory_candidates": []}


def _research(msg):
    return {"scope": "Audience", "sources_used": "Your request and profile; no live web research.",
            "audience_insights": [{"point": "The request focuses on growing an engaged local audience",
                                   "basis": "user_message"}],
            "competitor_insights": [], "content_gaps": ["Behind-the-scenes content"],
            "recommended_actions": ["Add competitor notes to the profile for a deeper comparison"],
            "uncertainties": ["No competitor data was provided."], "warnings": [], "memory_candidates": []}


def _report(msg):
    posts = re.search(r"Posts with figures: (\d+)", msg)
    imp = re.search(r"Impressions: ([\d,]+)", msg)
    head = (f"{posts.group(1)} posts recorded with {imp.group(1)} impressions" if posts and imp
            else "No performance figures recorded yet")
    return {"headline": head, "highlights": [], "what_to_improve": ["Record figures for every post"],
            "next_actions": ["Keep posting consistently"], "data_caveats": ["Figures were entered by the team."],
            "uncertainties": [], "warnings": []}


CREATOR_DEFAULTS = {"creator.content_writer": _content, "creator.brand_strategist": _brand,
                    "creator.calendar_planner": _calendar, "creator.campaign_planner": _campaign,
                    "creator.research_analyst": _research, "creator.report_writer": _report}


# ---------------------------------------------------------------- deterministic, validator-passing business outputs
_TAIL = {"uncertainties": [], "warnings": [], "memory_candidates": []}


def _line(msg: str, label: str) -> str | None:
    m = re.search(rf"^{label}:\s*(.+)$", msg, re.M)
    return m.group(1).strip() if m else None


def _competitors(msg):
    names = _line(msg, "Competitors to compare")
    return [n.strip() for n in names.split(",") if n.strip()] if names else []


def _b_profile(msg):
    return {"summary": "A local business serving the customers described in the profile.",
            "stage_assessment": "Early: building a base of regular customers.",
            "positioning_statement": "The dependable local choice for customers who value care.",
            "value_proposition": "Reliable service without the stress.",
            "customer_segments": [{"name": "Core customers", "description": "The customers named in the profile",
                                   "needs": ["reliability"], "buying_triggers": ["a specific need"],
                                   "where_to_reach": ["whatsapp", "instagram"]}],
            "competitive_landscape": [{"competitor": c, "what_we_know": "As noted in the profile",
                                       "how_to_stand_out": "Lead with your differentiators"} for c in _competitors(msg)],
            "channel_fit": [{"channel": "whatsapp", "fit": "strong", "why": "Customers already message you"},
                            {"channel": "google_business_profile", "fit": "possible", "why": "Helps local search"}],
            "priorities": ["Ask every happy customer for a review"], "risks": [],
            "data_gaps": ["How customers first hear about you"], **_TAIL}


def _b_positioning(msg):
    return {"positioning_statement": "The dependable local choice.", "value_proposition": "Less stress, more confidence.",
            "elevator_pitch": "We do the job properly and on time, so you don't have to worry.",
            "brand_personality": ["warm", "dependable"], "tone_guidance": "Friendly, plain and reassuring.",
            "key_messages": [{"audience": "Core customers", "message": "On time, every time.", "proof_points": []}],
            "taglines": ["Done right, on time.", "Care you can count on."], "words_to_use": ["fresh", "reliable"],
            "words_to_avoid": ["cheap"], "visual_direction": "Warm colours and real photos of your work.",
            "do_and_dont": ["Do show real customers (with permission)"], **_TAIL}


def _b_market(msg):
    focus = (_line(msg, "Focus") or "market").lower()
    comps = _competitors(msg) if focus == "competitors" else []
    return {"focus": focus, "sources_used": "Your profile and request; no live web research.",
            "market_insights": [] if focus == "competitors" else [
                {"point": "Your request is about understanding local demand", "basis": "user_message"}],
            "customer_insights": [{"point": "Customers described in your request value reliability", "basis": "user_message"}],
            "competitors": [{"competitor": c, "positioning": "As you described them", "strengths": [], "weaknesses": [],
                             "opportunity_for_us": "Make your differentiator obvious"} for c in comps],
            "questions_to_validate": ["Ask five recent customers why they chose you"],
            "recommendations": ["Collect reviews and show them"], **_TAIL}


def _b_plan(msg):
    n = int(re.search(r"(\d+)", _line(msg, "Plan length") or "3").group(1))
    return {"executive_summary": "Focus on the channels you already use, then add local search.", "plan_months": n,
            "objectives": [{"objective": "More customers", "metric": "new customers per month", "target": "[TARGET]"}],
            "target_segments": ["Core customers"],
            "channel_plan": [{"channel": "whatsapp", "role": "Orders and follow-up", "tactics": ["Status updates"],
                              "effort": "low", "budget_share": "No paid budget"}],
            "timeline": [{"period": f"Month {i}", "focus": "Build habits", "actions": ["Post and follow up"]}
                         for i in range(1, n + 1)],
            "budget": "Keep most of the stated budget for what proves itself.",
            "kpis": [{"metric": "enquiries", "how_to_measure": "Count WhatsApp enquiries"}], "risks": [], **_TAIL}


def _b_ads(msg):
    start, end = _range(msg)
    return {"objective": "More enquiries", "readiness_note": "Start small and measure enquiries.",
            "start_date": start.isoformat(), "end_date": end.isoformat(),
            "platforms": [{"channel": "meta_ads", "why": "Customers use Instagram and Facebook",
                           "audience_targeting": "People near your location", "formats": ["image"],
                           "budget_note": "A small test from your stated budget"}],
            "creatives": [{"channel": "meta_ads", "headline": "Done right, on time",
                           "primary_text": "Message us to order.", "call_to_action": "Send message"}],
            "test_plan": "Try two headlines for a week", "measurement": ["Enquiries from ads"],
            "compliance_notes": ["Check the platform's ad policies for your category"], **_TAIL}


def _b_growth(msg):
    focus = (_line(msg, "Focus") or "acquisition").lower()
    return {"focus": focus, "summary": f"A simple {focus} plan.",
            "journey": [{"stage": "First contact", "goal": "Reply fast"}, {"stage": "After purchase", "goal": "Follow up"}],
            "tactics": [{"name": "Follow-up message", "channel": "whatsapp", "how_it_works": "Message after each order",
                         "steps": ["Thank them"], "effort": "low", "cost_note": "Free", "metric": "repeat orders"},
                        {"name": "Referral ask", "channel": "referrals", "how_it_works": "Ask happy customers to refer",
                         "steps": ["Ask once"], "effort": "low", "cost_note": "[YOUR OFFER]", "metric": "referrals"}],
            "offers_or_hooks": [], "quick_wins": ["Message last month's customers"],
            "measurement": ["Repeat orders per month"], **_TAIL}


def _b_perf(msg):
    leads = _line(msg, "Leads")
    head = f"{leads} leads recorded" if leads and leads != "not recorded" else "No results recorded yet"
    return {"headline": head, "what_worked": [], "what_to_improve": ["Record results for every channel"],
            "budget_shifts": [], "next_actions": ["Keep recording results weekly"],
            "data_caveats": ["Figures were entered by the team."], "uncertainties": [], "warnings": []}


def _b_aida(msg):
    plats = _platforms(msg, ("instagram", "whatsapp"))
    stage = lambda st, i: {"stage": st, "goal": f"{st.title()} goal", "key_message": "Reliable and local",  # noqa: E731
                           "posts": [{"platform": plats[i % len(plats)], "format": "post", "idea": f"{st} idea",
                                      "draft_copy": f"A short {st} post.", "call_to_action": "Message us"}]}
    return {"objective": "More enquiries from social", "audience": "Local customers", "platforms": plats,
            "stages": [stage(s, i) for i, s in enumerate(("attention", "interest", "desire", "action"))],
            "posting_rhythm": "A few posts a week", "kpis": [{"metric": "enquiries", "why": "Easy to count"}],
            "budget_note": "Mostly time; no paid budget needed to start.", **_TAIL}


BUSINESS_DEFAULTS = {"business.profile_builder": _b_profile, "business.positioning_strategist": _b_positioning,
                     "business.market_analyst": _b_market, "business.marketing_planner": _b_plan,
                     "business.ads_planner": _b_ads, "business.growth_strategist": _b_growth,
                     "business.performance_analyst": _b_perf, "business.aida_strategist": _b_aida}


# ---------------------------------------------------------------- deterministic, validator-passing freelancer outputs
def _first(refs, prefix):
    return next((k for k in refs if k.startswith(prefix)), None)


def _field(refs, ref, key, default=""):
    try:
        return json.loads(refs[ref]).get(key, default)
    except (KeyError, ValueError, AttributeError):
        return default


def _f_assess(msg, refs):
    skills = [k for k in refs if k.startswith("profile:skills")]
    shown = _first(refs, "profile:portfolio") or _first(refs, "profile:experiences")
    rows = []
    for i, k in enumerate(skills[:4]):
        name = _field(refs, k, "name", "Skill")
        rows.append({"skill": name, "evidence_level": "shown" if (i == 0 and shown) else "stated",
                     "evidence_refs": [k, shown] if (i == 0 and shown) else [k], "note": "From your profile"})
    rows.append({"skill": "Prototyping", "evidence_level": "suggested", "evidence_refs": [], "note": "Worth adding"})
    return {"summary": "You have real, evidenced design skills and are ready for first paid work.",
            "stage_read": "Early career: building client proof.", "skills": rows,
            "strengths": ["Clear, simple interface work"],
            "gaps": [{"gap": "Paid client work", "why_it_matters": "Clients look for proof",
                      "how_to_close": "One small paid project or a well-labelled practice project"}],
            "suggested_directions": [{"title": "Onboarding UX audits", "kind": "service", "why": "Fits your case study"}],
            "headline_options": ["UI/UX designer for fintech onboarding"], "missing_information": [] if refs else ["your profile"],
            "uncertainties": [], "warnings": [], "memory_candidates": []}


def _f_cv(msg, refs):
    market = (_line(msg, "Target market") or "global_remote").strip()
    role = (_line(msg, "Target role") or "Designer").strip()
    exp = []
    for k in [r for r in refs if r.startswith("profile:experiences")][:3]:
        bullets = [{"text": a, "source_ref": k} for a in _field(refs, k, "achievements", [])[:3]]
        exp.append({"title": _field(refs, k, "title"), "organisation": _field(refs, k, "organisation"),
                    "period": _field(refs, k, "period"), "source_ref": k, "bullets": bullets})
    items = lambda p, key: [{"name": _field(refs, k, key), "detail": "", "source_ref": k}  # noqa: E731
                            for k in refs if k.startswith(p)][:8]
    return {"target_role": role, "market": market, "headline": f"{role} candidate",
            "summary": "Designer focused on clear, simple product experiences.", "experience": exp,
            "projects": items("profile:portfolio", "title"), "skills": items("profile:skills", "name"),
            "education": items("profile:education", "qualification"),
            "certifications": items("profile:certifications", "name"), "keywords_matched": [],
            "keywords_missing": [], "tailoring_notes": ["Ordered to match the role"],
            "suggestions": ["Suggestion: add one measurable result if you have it"],
            "missing_information": [] if refs else ["your profile"], "uncertainties": [], "warnings": [],
            "memory_candidates": []}


def _f_interview(msg, refs):
    story_ref = _first(refs, "profile:portfolio") or _first(refs, "profile:experiences")
    n = int(_line(msg, "Question count") or 5)
    qs = [{"question": f"Practice question {i}: tell me about your work", "type": "behavioural",
           "why_asked": "To understand how you work", "answer_outline": "Use a real project: situation, action, result",
           "story_ref": story_ref} for i in range(1, n + 1)]
    stories = [{"title": "A real project", "situation": "A product needed a clearer flow", "task": "Improve it",
                "action": "Mapped the flow and simplified it", "result": "[ADD RESULT]", "source_ref": story_ref}] if story_ref else []
    return {"role": (_line(msg, "Role") or "the role").strip(), "company_notes": [], "questions": qs, "stories": stories,
            "questions_to_ask": ["What does success look like in the first 90 days?"],
            "logistics": ["Confirm the interview time in your own time zone"],
            "missing_information": [] if refs else ["your profile"], "uncertainties": [], "warnings": [],
            "memory_candidates": []}


def _f_answer(msg, refs):
    return {"scores": {"structure": 3, "relevance": 4, "specificity": 2, "clarity": 4},
            "overall": "Relevant answer; add what you did and what changed.", "strengths": ["You used a real example"],
            "improvements": ["Use situation, action, result", "Add one concrete result"],
            "improved_answer": "In that project I mapped the problem, simplified the flow and tested it. [ADD RESULT]",
            "follow_up_question": "How did you know it worked?", "uncertainties": [], "warnings": []}


def _f_case(msg, refs):
    ref = _first(refs, "profile:portfolio") or _first(refs, "profile:experiences") or "user_message"
    return {"title": _field(refs, ref, "title", "Project case study") if ref != "user_message" else "Project case study",
            "project_ref": ref, "client_label": "A confidential client", "summary": "A short story of a real project.",
            "challenge": "The product's flow was confusing.", "approach": ["Mapped the flow", "Simplified the steps"],
            "my_role": "Designer", "outcome": "[ADD RESULT]", "skills_used": ["Figma"], "testimonial": None,
            "visuals_to_add": ["Before/after screens"], "missing_information": ["A result you can share"],
            "uncertainties": [], "warnings": [], "memory_candidates": []}


def _f_brand(msg, refs):
    plats = [p.strip() for p in (_line(msg, "Platforms") or "linkedin").split(",")]
    post_plats = [p for p in plats if p in ("linkedin", "x", "instagram", "threads", "facebook", "tiktok")] or ["linkedin"]
    return {"positioning_line": "Designer making products simpler to use",
            "bios": [{"platform": "x", "text": "Designer. Simple, clear product experiences."},
                     {"platform": "linkedin", "text": "I design clear, simple product experiences."}],
            "posts": [{"platform": p, "hook": "What I learned simplifying a sign-up flow",
                       "text": "A short lesson from a real project: fewer steps, clearer words."} for p in post_plats],
            "content_ideas": ["Before/after breakdowns"], "claims": [],
            "missing_information": [] if refs else ["your profile"], "uncertainties": [], "warnings": [],
            "memory_candidates": []}


def _f_outreach(msg, refs):
    return {"offer_summary": "A focused service for teams that need clearer products",
            "ideal_clients": [{"segment": "Early-stage startups", "why_fit": "They need quick, practical help",
                               "where_to_find": ["LinkedIn", "founder communities"], "buying_signals": ["New launch"]}],
            "prospects": [], "research_checklist": ["Use their product first", "Find the right person"],
            "messages": [{"channel": "linkedin", "purpose": "first_touch", "subject": None,
                          "text": "Hi [NAME], I noticed [DETAIL] in your product. I help teams make this simpler. Open to a quick chat?"},
                         {"channel": "email", "purpose": "follow_up", "subject": "Quick follow-up",
                          "text": "Hi [NAME], following up on my note about [DETAIL]."}],
            "weekly_routine": ["Research 10 prospects", "Send 5 personalised messages"], "metrics": ["Reply rate"],
            "claims": [], "missing_information": [] if refs else ["your profile"], "uncertainties": [], "warnings": [],
            "memory_candidates": []}


def _f_pricing(msg, refs):
    text = " ".join(refs.values()) + " " + msg
    cur = (re.findall(r"\b(?!USD)[A-Z]{3}\b", text) or re.findall(r"\bUSD\b", text) or ["USD"])[0]
    floor = _line(msg, "Rate floor")
    pk = lambda name, model, lo, hi, basis: {"name": name, "for_who": "Small teams", "deliverables": ["Defined output"],  # noqa: E731
                                            "timeline": "1 week", "pricing_model": model, "price_low": lo,
                                            "price_high": hi, "currency": cur, "basis": basis,
                                            "rationale": "A clear, low-risk offer to start with"}
    packages = [pk("Starter", "fixed", 100, 150, "suggested_starting_point")]
    if floor:
        m = re.match(r"([A-Z]{3}) ([\d.,]+)", floor)
        if m:
            fl = float(m.group(2).replace(",", ""))
            packages.append({**pk("Hourly support", "hourly", round(fl * 1.5, 2), round(fl * 2, 2), "your_income_goal"),
                             "currency": m.group(1)})
    return {"packages": packages, "pricing_notes": ["Review prices after every 3 projects"],
            "scope_protection": ["Take a deposit", "Agree the number of revisions"],
            "cross_border": ["Check how the client can pay you and the fees on both sides before you start"],
            "upsells": ["Ongoing monthly support"], "missing_information": [], "uncertainties": [], "warnings": [],
            "memory_candidates": []}


def _f_learning(msg, refs):
    n = int(_line(msg, "Weeks") or 4)
    return {"goal": (_line(msg, "Goal") or "Grow my skills").strip(), "starting_point": "From your profile",
            "weeks": [{"week": i, "focus": f"Week {i} focus", "activities": ["Learn", "Practise", "Build"],
                       "resources": [{"name": "ALX Africa", "url": "https://www.alxafrica.com", "cost": "unknown"}] if i == 1 else [],
                       "output": "A small portfolio piece"} for i in range(1, n + 1)],
            "milestones": ["A new case study"], "portfolio_outputs": ["One finished project"],
            "missing_information": [], "uncertainties": [], "warnings": [], "memory_candidates": []}


def _f_opportunity(msg, refs):
    elig = (_line(msg, "Eligibility \\(computed\\)") or "unclear").split()[0]
    flags = (_line(msg, "Red flags \\(computed\\)") or "none").strip()
    skill = _first(refs, "profile:skills")
    rec = "skip_or_clarify" if elig == "not_eligible" or flags != "none" else "apply_after_checks"
    return {"summary": "The listing describes a role; details are as the listing states them.",
            "requirements": [{"requirement": "Relevant skills", "met": "yes" if skill else "unknown", "profile_ref": skill}],
            "strengths_to_lead_with": [{"point": "Your listed skills", "profile_ref": skill}] if skill else [],
            "gaps": [], "eligibility_comment": f"Computed eligibility: {elig}" + (" (you're not eligible)" if elig == "not_eligible" else ""),
            "timezone_comment": "See the computed overlap.", "red_flags": [] if flags == "none" else [flags],
            "verify_before_applying": ["The posting is live on the company's own website", "The pay and how it is paid"],
            "recommendation": rec, "recommendation_reason": "Based on the checks above.",
            "application_angle": "Lead with your strongest real project.", "uncertainties": [], "warnings": [],
            "memory_candidates": []}


def _f_proposal(msg, refs):
    exp = _first(refs, "profile:experiences") or _first(refs, "profile:portfolio")
    claim = [{"claim": _field(refs, exp, "title") or "Relevant work", "source_ref": exp}] if exp else []
    has_rates = any(k.startswith("profile:rates") for k in refs)
    return {"document_type": "cover_letter" if "cover letter" in msg.lower() else "proposal",
            "title": "Application", "opening": "Hello, I'd like to help with this.",
            "sections": [{"heading": "Why me", "text": "I've done similar work, described in my profile."}],
            "pricing": "As discussed in my rates." if has_rates else "[YOUR RATE]",
            "closing": "Thank you for considering me.", "claims": claim,
            "missing_information": [] if refs else ["your profile"], "uncertainties": [], "warnings": [],
            "memory_candidates": []}


FREELANCER_DEFAULTS = {"freelancer.skills_assessor": _f_assess, "freelancer.cv_writer": _f_cv,
                       "freelancer.interview_coach": _f_interview, "freelancer.answer_coach": _f_answer,
                       "freelancer.portfolio_builder": _f_case, "freelancer.brand_writer": _f_brand,
                       "freelancer.outreach_planner": _f_outreach, "freelancer.pricing_advisor": _f_pricing,
                       "freelancer.learning_planner": _f_learning, "freelancer.opportunity_analyst": _f_opportunity,
                       "freelancer.proposal_writer": _f_proposal}
