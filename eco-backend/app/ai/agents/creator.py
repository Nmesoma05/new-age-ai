"""Creator & Marketing division agents (in addition to creator.assistant and creator.content_writer).

Each spec is self-contained: instructions, read-only tools, a strict output schema and validators enforced in code.
None of these agents can publish or claim results; performance figures only ever come from data the user recorded.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import Field

from app.ai.agents.base import (
    READ_TOOLS,
    AgentContext,
    AgentOutput,
    AgentSpec,
    Issue,
    Platform,
    PrimaryOutput,
    RunState,
    Strict,
    no_action_claims,
    no_invented_numbers,
)

CREATOR = frozenset({"creator"})
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RANGE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*(?:to|-|–|until)\s*(\d{4}-\d{2}-\d{2})")
_PLATFORMS_LINE = re.compile(r"^Platforms:\s*(.+)$", re.M | re.I)


def _parse_date(s: str) -> date | None:
    if not _DATE.match(s or ""):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def requested_range(state: RunState) -> tuple[date, date] | None:
    m = _RANGE.search(state.user_message)
    if not m:
        return None
    a, b = _parse_date(m.group(1)), _parse_date(m.group(2))
    return (a, b) if a and b and a <= b else None


def requested_platforms(state: RunState) -> set[str] | None:
    m = _PLATFORMS_LINE.search(state.user_message)
    if not m:
        return None
    return {p.strip().lower() for p in m.group(1).split(",") if p.strip()}


# ====================================================================== brand strategist
class VoiceTrait(Strict):
    trait: str = Field(max_length=60, description="e.g. Warm")
    what_it_means: str = Field(max_length=300)
    avoid: str = Field(max_length=300, description="What this trait is NOT")


class PlatformTone(Strict):
    platform: Platform
    guidance: str = Field(max_length=400)


class Persona(Strict):
    name: str = Field(max_length=80, description="A label, e.g. 'Busy Lagos professional'")
    description: str = Field(max_length=500)
    needs: list[str] = Field(default_factory=list, max_length=6)
    where_they_spend_time: list[Platform] = Field(default_factory=list, max_length=6)


class Pillar(Strict):
    name: str = Field(max_length=60)
    purpose: str = Field(max_length=300)
    example_topics: list[str] = Field(default_factory=list, max_length=6)


class BrandStrategy(PrimaryOutput):
    positioning: str = Field(max_length=800, description="One short paragraph: who it's for, what it offers, why it's different")
    voice_attributes: list[VoiceTrait] = Field(min_length=2, max_length=6)
    tone_by_platform: list[PlatformTone] = Field(default_factory=list, max_length=9)
    words_to_use: list[str] = Field(default_factory=list, max_length=15)
    words_to_avoid: list[str] = Field(default_factory=list, max_length=15)
    sample_lines: list[str] = Field(min_length=2, max_length=6, description="Example sentences in this voice")
    audience_personas: list[Persona] = Field(default_factory=list, max_length=4)
    content_pillars: list[Pillar] = Field(min_length=2, max_length=6)

    def render(self) -> str:
        out = [f"**Positioning:** {self.positioning}", "### Voice"]
        out += [f"- **{v.trait}**: {v.what_it_means} _Not: {v.avoid}_" for v in self.voice_attributes]
        if self.tone_by_platform:
            out.append("### By platform\n" + "\n".join(f"- **{t.platform}**: {t.guidance}" for t in self.tone_by_platform))
        if self.words_to_use or self.words_to_avoid:
            out.append(f"**Say:** {', '.join(self.words_to_use) or '—'}  \n**Avoid:** {', '.join(self.words_to_avoid) or '—'}")
        out.append("### Sounds like\n" + "\n".join(f"> {s}" for s in self.sample_lines))
        if self.audience_personas:
            out.append("### Audience\n" + "\n".join(f"- **{p.name}**: {p.description}" for p in self.audience_personas))
        out.append("### Content pillars\n" + "\n".join(f"- **{p.name}**: {p.purpose}" for p in self.content_pillars))
        return "\n\n".join(out)


BRAND_STRATEGIST = AgentSpec(
    name="creator.brand_strategist", kind="primary", products=CREATOR,
    purpose="turn what's known about this client into a usable brand voice profile, audience personas and content pillars.",
    instructions="""
Call get_profile first, then search_context for brand rules and good past posts. Build on what the client already
has; don't contradict saved brand rules. Personas describe kinds of people, not invented statistics. If key facts
are missing (what they sell, who buys), say so in uncertainties and keep the profile general rather than guessing.
""",
    output_model=BrandStrategy, tools=READ_TOOLS, saves_as="brand_voice", max_tokens=3500,
    validators=(no_action_claims,
                no_invented_numbers(lambda o: [o.positioning, *o.sample_lines, *(p.description for p in o.audience_personas)])))


# ====================================================================== calendar planner
class CalendarEntry(Strict):
    date: str = Field(description="YYYY-MM-DD")
    time: str = Field(description="Suggested local time HH:MM (24h)")
    platform: Platform
    format: Literal["post", "thread", "carousel", "reel", "story", "video", "short", "live", "article", "pin"]
    pillar: str = Field(max_length=60)
    title: str = Field(max_length=120)
    idea: str = Field(max_length=500)


class ContentCalendarPlan(PrimaryOutput):
    strategy_summary: str = Field(max_length=1200, description="The social strategy for this period in plain words")
    start_date: str
    end_date: str
    posting_rhythm: str = Field(max_length=500)
    items: list[CalendarEntry] = Field(min_length=1, max_length=62)

    def render(self) -> str:
        rows = "\n".join(f"| {i.date} {i.time} | {i.platform} | {i.format} | {i.pillar} | {i.title} |" for i in self.items)
        return (f"**Strategy:** {self.strategy_summary}\n\n**Rhythm:** {self.posting_rhythm}\n\n"
                f"| When | Platform | Format | Pillar | Post |\n|---|---|---|---|---|\n{rows}")


def _calendar_checks(out: ContentCalendarPlan, state: RunState, ctx: AgentContext) -> list[Issue]:
    issues: list[Issue] = []
    start, end = _parse_date(out.start_date), _parse_date(out.end_date)
    if not start or not end or start > end:
        return [Issue("error", "start_date and end_date must be valid YYYY-MM-DD dates with start before end.")]
    want = requested_range(state)
    if want and (start, end) != want:
        issues.append(Issue("error", f"The plan must cover exactly {want[0]} to {want[1]}."))
    lo, hi = want or (start, end)  # the requested period wins over whatever the plan claims
    bad_dates = [i.date for i in out.items if not (_parse_date(i.date) and lo <= _parse_date(i.date) <= hi)]
    if bad_dates:
        issues.append(Issue("error", f"These dates are invalid or outside the period: {', '.join(bad_dates[:5])}."))
    bad_times = [i.time for i in out.items if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", i.time)]
    if bad_times:
        issues.append(Issue("error", "Times must be HH:MM in 24-hour format."))
    platforms = requested_platforms(state)
    if platforms:
        stray = {i.platform for i in out.items} - platforms
        if stray:
            issues.append(Issue("error", f"Only plan for the requested platforms; remove {', '.join(sorted(stray))}."))
    return issues


CALENDAR_PLANNER = AgentSpec(
    name="creator.calendar_planner", kind="primary", products=CREATOR,
    purpose="create a social media strategy and a dated content calendar for this client.",
    instructions="""
Call get_profile (platforms, audience, goals, pillars) and search_context (brand rules, past posts) first. Then plan
a realistic schedule the team can actually produce: spread pillars, mix formats, avoid repeating past ideas.
Use exactly the period and platforms in the request. Times are suggestions in the client's local time; you don't
know their best posting times, so say so in uncertainties unless the user gave them. Give each slot a working
title and a one-line idea, not the full post.
""",
    output_model=ContentCalendarPlan, tools=READ_TOOLS, saves_as="calendar_plan", max_tokens=6000,
    validators=(no_action_claims, _calendar_checks,
                no_invented_numbers(lambda o: [o.strategy_summary, *(i.idea for i in o.items)])))


# ====================================================================== campaign planner
class Deliverable(Strict):
    platform: Platform
    format: str = Field(max_length=40)
    description: str = Field(max_length=300)


class Phase(Strict):
    name: str = Field(max_length=80)
    start_date: str
    end_date: str
    goal: str = Field(max_length=300)
    activities: list[str] = Field(default_factory=list, max_length=8)
    deliverables: list[Deliverable] = Field(default_factory=list, max_length=12)


class CampaignKpi(Strict):
    metric: str = Field(max_length=120)
    how_to_measure: str = Field(max_length=300)


class CampaignPlan(PrimaryOutput):
    name: str = Field(max_length=160)
    objective: str = Field(max_length=600)
    audience: str = Field(max_length=600)
    key_message: str = Field(max_length=400)
    start_date: str
    end_date: str
    channels: list[Platform] = Field(min_length=1, max_length=9)
    phases: list[Phase] = Field(min_length=1, max_length=6)
    kpis: list[CampaignKpi] = Field(min_length=1, max_length=8)
    budget_note: str = Field(max_length=600, description="What it needs in money and time; no invented prices")
    risks: list[str] = Field(default_factory=list, max_length=6)

    def render(self) -> str:
        out = [f"## {self.name}", f"**Objective:** {self.objective}", f"**Audience:** {self.audience}",
               f"**Key message:** {self.key_message}", f"**When:** {self.start_date} to {self.end_date} · "
               f"**Channels:** {', '.join(self.channels)}"]
        for p in self.phases:
            out.append(f"### {p.name} ({p.start_date} to {p.end_date})\n{p.goal}\n"
                       + "\n".join(f"- {a}" for a in p.activities)
                       + ("\n" + "\n".join(f"- **{d.platform} {d.format}:** {d.description}" for d in p.deliverables)
                          if p.deliverables else ""))
        out.append("**Measure:** " + "; ".join(f"{k.metric} ({k.how_to_measure})" for k in self.kpis))
        out.append(f"**Budget:** {self.budget_note}")
        if self.risks:
            out.append("**Risks:** " + "; ".join(self.risks))
        return "\n\n".join(out)


def _campaign_checks(out: CampaignPlan, state: RunState, ctx: AgentContext) -> list[Issue]:
    start, end = _parse_date(out.start_date), _parse_date(out.end_date)
    if not start or not end or start > end:
        return [Issue("error", "start_date and end_date must be valid YYYY-MM-DD dates with start before end.")]
    issues: list[Issue] = []
    want = requested_range(state)
    if want and (start, end) != want:
        issues.append(Issue("error", f"The campaign must run exactly {want[0]} to {want[1]}."))
    for p in out.phases:
        ps, pe = _parse_date(p.start_date), _parse_date(p.end_date)
        if not ps or not pe or ps > pe or ps < start or pe > end:
            issues.append(Issue("error", f"Phase '{p.name}' dates must be valid and inside the campaign dates."))
    stray = {d.platform for p in out.phases for d in p.deliverables} - set(out.channels)
    if stray:
        issues.append(Issue("error", f"Deliverables use channels not in the plan: {', '.join(sorted(stray))}."))
    return issues


CAMPAIGN_PLANNER = AgentSpec(
    name="creator.campaign_planner", kind="primary", products=CREATOR,
    purpose="plan a marketing campaign for this client: objective, phases, channels, deliverables and how to measure it.",
    instructions="""
Call get_profile and search_context first. Plan phases that fit inside the requested dates (e.g. tease, launch,
sustain). Deliverables say what to make for each channel. KPIs are things the team can count from platform
insights; don't invent targets, benchmarks or prices: use [TARGET] or [YOUR BUDGET] placeholders.
""",
    output_model=CampaignPlan, tools=READ_TOOLS, saves_as="campaign_plan", max_tokens=5000,
    validators=(no_action_claims, _campaign_checks,
                no_invented_numbers(lambda o: [o.objective, o.key_message, o.budget_note,
                                               *(k.metric for k in o.kpis), *(p.goal for p in o.phases)])))


# ====================================================================== research analyst
class Basis(Strict):
    point: str = Field(max_length=400)
    basis: str = Field(description="Where this comes from: a profile:… ref, a doc:… ref, a URL from search results, "
                                   "or user_message")


class CompetitorInsight(Strict):
    competitor: str = Field(max_length=120)
    observations: list[Basis] = Field(default_factory=list, max_length=6)
    opportunities: list[str] = Field(default_factory=list, max_length=5)


class ResearchReport(PrimaryOutput):
    scope: str = Field(max_length=300)
    sources_used: str = Field(max_length=400, description="Plainly: what this is based on, e.g. 'your profile and the "
                                                        "competitor notes you added; no live web research'")
    audience_insights: list[Basis] = Field(default_factory=list, max_length=8)
    competitor_insights: list[CompetitorInsight] = Field(default_factory=list, max_length=6)
    content_gaps: list[str] = Field(default_factory=list, max_length=6)
    recommended_actions: list[str] = Field(min_length=1, max_length=8)

    def render(self) -> str:
        out = [f"**Scope:** {self.scope}", f"_Based on: {self.sources_used}_"]
        if self.audience_insights:
            out.append("### Audience\n" + "\n".join(f"- {a.point}" for a in self.audience_insights))
        for c in self.competitor_insights:
            out.append(f"### {c.competitor}\n" + "\n".join(f"- {o.point}" for o in c.observations)
                       + ("\n**Opportunities:** " + "; ".join(c.opportunities) if c.opportunities else ""))
        if self.content_gaps:
            out.append("### Content gaps\n" + "\n".join(f"- {g}" for g in self.content_gaps))
        out.append("### Do next\n" + "\n".join(f"- {r}" for r in self.recommended_actions))
        return "\n\n".join(out)


def _research_basis(out: ResearchReport, state: RunState, ctx: AgentContext) -> list[Issue]:
    def ok(b: str) -> bool:
        return b == "user_message" or b in state.refs_seen or b in state.urls_seen or b in state.profile_refs

    points = [*out.audience_insights, *(o for c in out.competitor_insights for o in c.observations)]
    bad = [p.point for p in points if not ok(p.basis)]
    issues = []
    if bad:
        issues.append(Issue("error", "Each insight must cite where it came from (a profile or doc ref you read, a "
                                     "search result URL, or user_message). Unsupported: " + "; ".join(bad[:3])))
    corpus = " ".join(state.corpus + [state.user_message]).lower()
    unknown = [c.competitor for c in out.competitor_insights if c.competitor.lower() not in corpus]
    if unknown:
        issues.append(Issue("error", f"Only analyse competitors named by the user or in the profile: {', '.join(unknown)}"))
    if not state.urls_seen and re.search(r"\b(web|online|live) research\b", out.sources_used, re.I) and \
            "no " not in out.sources_used.lower():
        issues.append(Issue("error", "No web research was done in this run; don't say it was."))
    return issues


RESEARCH_ANALYST = AgentSpec(
    name="creator.research_analyst", kind="primary", products=CREATOR,
    purpose="analyse this client's audience and competitors using only information that's actually available.",
    instructions="""
Call get_profile (audience, competitors, goals) and search_context (notes, uploaded research). Analyse only
competitors the user named. Every insight cites its basis. You can't see competitors' accounts or follower counts
unless the user or a source provided them: say what would need checking by hand. State plainly in sources_used
whether any live web research was involved (it usually isn't).
""",
    output_model=ResearchReport, tools=READ_TOOLS, saves_as="research", max_tokens=4000,
    validators=(no_action_claims, _research_basis,
                no_invented_numbers(lambda o: [*(a.point for a in o.audience_insights),
                                               *(x.point for c in o.competitor_insights for x in c.observations)])))


# ====================================================================== report writer
class Highlight(Strict):
    point: str = Field(max_length=400)
    metric_basis: str = Field(max_length=200, description="Which recorded figure(s) this is based on")


class PerformanceNarrative(AgentOutput):
    headline: str = Field(max_length=300)
    highlights: list[Highlight] = Field(default_factory=list, max_length=6)
    what_to_improve: list[str] = Field(default_factory=list, max_length=6)
    next_actions: list[str] = Field(min_length=1, max_length=6)
    data_caveats: list[str] = Field(min_length=1, max_length=5,
                                    description="Limits of the data, e.g. entered by hand, missing platforms, small sample")

    def render(self) -> str:
        out = [f"**{self.headline}**", *(f"- {h.point}" for h in self.highlights)]
        if self.what_to_improve:
            out.append("**Improve:**\n" + "\n".join(f"- {w}" for w in self.what_to_improve))
        out.append("**Next:**\n" + "\n".join(f"- {n}" for n in self.next_actions))
        out.append("_About this data: " + " ".join(self.data_caveats) + "_")
        return "\n\n".join(out)


_ANY_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?%?")


def strict_numbers(texts: list[str], state: RunState) -> list[Issue]:
    """Stricter than the shared check: every number must come from the recorded data given in the task."""
    corpus = " ".join(state.corpus + [state.user_message])
    known = {n.replace(",", "").rstrip("%") for n in _ANY_NUMBER.findall(corpus)}
    bad = sorted({n for t in texts for n in _ANY_NUMBER.findall(t)
                  if len(n.replace(",", "").rstrip("%")) > 1 and n.replace(",", "").rstrip("%") not in known})
    if bad:
        return [Issue("error", f"These numbers aren't in the recorded data: {', '.join(bad[:6])}. Use only the "
                               "figures provided.")]
    return []


def _report_numbers(out: PerformanceNarrative, state: RunState, ctx: AgentContext) -> list[Issue]:
    return strict_numbers([out.headline, *(h.point for h in out.highlights), *out.what_to_improve,
                           *out.next_actions], state)


REPORT_WRITER = AgentSpec(
    name="creator.report_writer", kind="primary", products=CREATOR,
    purpose="explain this client's recorded performance numbers in plain words and suggest what to do next.",
    instructions="""
The task contains a performance summary calculated by the system from data the team recorded (manually or by
file upload). Use only those figures; don't estimate missing ones or compare with industry benchmarks. Point
out what worked and what to try next. Always include caveats about the data (who entered it, missing
platforms or dates, small numbers of posts).
""",
    output_model=PerformanceNarrative, tools=("get_profile", "search_context"), saves_as="report", max_tokens=2500,
    validators=(no_action_claims, _report_numbers))


CREATOR_AGENTS = (BRAND_STRATEGIST, CALENDAR_PLANNER, CAMPAIGN_PLANNER, RESEARCH_ANALYST, REPORT_WRITER)
