"""Business Marketing division agents (alongside business.assistant and business.aida_strategist).

Every request to these agents is prefixed with the business context (category, stage, location, budget, channels)
by the API, so recommendations start from the actual business. Validators hold them to the facts given:
no invented figures, only named competitors, research claims tied to a source, plans matching what was asked.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import Field

from app.ai.agents.base import (
    READ_TOOLS,
    AgentContext,
    AgentOutput,
    AgentSpec,
    Issue,
    PrimaryOutput,
    RunState,
    Strict,
    _nums,
    no_action_claims,
    no_invented_numbers,
)
from app.ai.agents.creator import _parse_date, requested_range, strict_numbers

BUSINESS = frozenset({"business"})
Channel = Literal["instagram", "facebook", "tiktok", "x", "linkedin", "youtube", "whatsapp", "google_search_ads",
                  "meta_ads", "email", "sms", "website_seo", "google_business_profile", "marketplaces", "referrals",
                  "events", "partnerships", "print_outdoor", "radio_tv", "sales_outreach", "other"]
AdChannel = Literal["meta_ads", "google_search_ads", "tiktok", "linkedin", "youtube", "x", "instagram", "facebook"]
Effort = Literal["low", "medium", "high"]
RULES = """
The task starts with the business context and general guidance for its category and stage. Use the guidance only
where it fits this business's facts; the profile and the user's words win. Recommendations must suit the stated
location, customers, budget and stage (e.g. no large ad budgets for an idea-stage business). Never invent figures,
prices, market sizes, statistics or competitor details: use [TARGET], [YOUR PRICE] or say it needs checking.
"""


def _named_competitors_only(names: list[str], state: RunState) -> list[Issue]:
    corpus = " ".join(state.corpus + [state.user_message]).lower()
    unknown = [n for n in names if n.lower() not in corpus]
    return [Issue("error", f"Only discuss competitors the user named or that are in the profile: {', '.join(unknown)}")] \
        if unknown else []


def _basis_ok(b: str, state: RunState) -> bool:
    return b == "user_message" or b in state.refs_seen or b in state.urls_seen or b in state.profile_refs


def _requested(pattern: str, state: RunState) -> str | None:
    m = re.search(pattern, state.user_message, re.I | re.M)
    return m.group(1).strip().lower() if m else None


# ====================================================================== 1. Marketing Intelligence Profile builder
class Segment(Strict):
    name: str = Field(max_length=80)
    description: str = Field(max_length=500)
    needs: list[str] = Field(default_factory=list, max_length=6)
    buying_triggers: list[str] = Field(default_factory=list, max_length=5)
    where_to_reach: list[Channel] = Field(default_factory=list, max_length=6)


class CompetitorNote(Strict):
    competitor: str = Field(max_length=120)
    what_we_know: str = Field(max_length=400, description="Only from the profile or the user")
    how_to_stand_out: str = Field(max_length=400)


class ChannelFit(Strict):
    channel: Channel
    fit: Literal["strong", "possible", "weak"]
    why: str = Field(max_length=300)


class IntelligenceProfile(PrimaryOutput):
    summary: str = Field(max_length=900, description="What the business is, for whom, and its marketing situation")
    stage_assessment: str = Field(max_length=500)
    positioning_statement: str = Field(max_length=400)
    value_proposition: str = Field(max_length=400)
    customer_segments: list[Segment] = Field(min_length=1, max_length=4)
    competitive_landscape: list[CompetitorNote] = Field(default_factory=list, max_length=6)
    channel_fit: list[ChannelFit] = Field(min_length=2, max_length=8)
    priorities: list[str] = Field(min_length=1, max_length=5, description="What to focus on in the next 90 days")
    risks: list[str] = Field(default_factory=list, max_length=5)
    data_gaps: list[str] = Field(default_factory=list, max_length=6, description="Facts that would improve the advice")

    def render(self) -> str:
        out = [self.summary, f"**Stage:** {self.stage_assessment}", f"**Positioning:** {self.positioning_statement}",
               f"**Value proposition:** {self.value_proposition}", "### Customers"]
        out += [f"- **{s.name}**: {s.description}" for s in self.customer_segments]
        if self.competitive_landscape:
            out.append("### Competitors\n" + "\n".join(f"- **{c.competitor}**: {c.what_we_know} _Stand out:_ {c.how_to_stand_out}"
                                                         for c in self.competitive_landscape))
        out.append("### Channel fit\n" + "\n".join(f"- **{c.channel}** ({c.fit}): {c.why}" for c in self.channel_fit))
        out.append("### Priorities\n" + "\n".join(f"- {p}" for p in self.priorities))
        if self.data_gaps:
            out.append("### To improve this profile, add\n" + "\n".join(f"- {g}" for g in self.data_gaps))
        return "\n\n".join(out)


def _profile_checks(out: IntelligenceProfile, state: RunState, ctx: AgentContext) -> list[Issue]:
    return _named_competitors_only([c.competitor for c in out.competitive_landscape], state)


PROFILE_BUILDER = AgentSpec(
    name="business.profile_builder", kind="primary", products=BUSINESS,
    purpose="turn the owner's onboarding answers into a clear, editable Marketing Intelligence Profile.",
    instructions=RULES + """
Call get_profile first. Summarise plainly for a non-marketer. Customer segments come from what the owner said
about customers (don't invent demographics or percentages). Rate channel fit for this business's category, stage,
location and budget, including channels it already uses. List data_gaps for anything important that's missing.
""",
    output_model=IntelligenceProfile, tools=("get_profile", "search_context"), saves_as="intelligence_profile",
    max_tokens=4500,
    validators=(no_action_claims, _profile_checks,
                no_invented_numbers(lambda o: [o.summary, o.stage_assessment, o.value_proposition, *o.priorities,
                                               *(s.description for s in o.customer_segments)])))


# ====================================================================== 2. positioning, brand identity & messaging
class KeyMessage(Strict):
    audience: str = Field(max_length=100)
    message: str = Field(max_length=300)
    proof_points: list[str] = Field(default_factory=list, max_length=4, description="Facts from the profile that back it")


class PositioningGuide(PrimaryOutput):
    positioning_statement: str = Field(max_length=400)
    value_proposition: str = Field(max_length=400)
    elevator_pitch: str = Field(max_length=500)
    brand_personality: list[str] = Field(min_length=2, max_length=5)
    tone_guidance: str = Field(max_length=500)
    key_messages: list[KeyMessage] = Field(min_length=1, max_length=5)
    taglines: list[str] = Field(min_length=2, max_length=5)
    words_to_use: list[str] = Field(default_factory=list, max_length=12)
    words_to_avoid: list[str] = Field(default_factory=list, max_length=12)
    visual_direction: str = Field(max_length=500, description="Described in words: colours, imagery, feel")
    do_and_dont: list[str] = Field(default_factory=list, max_length=8)

    def render(self) -> str:
        out = [f"**Positioning:** {self.positioning_statement}", f"**Value proposition:** {self.value_proposition}",
               f"**Elevator pitch:** {self.elevator_pitch}",
               f"**Personality:** {', '.join(self.brand_personality)}. {self.tone_guidance}", "### Key messages"]
        out += [f"- **{m.audience}**: {m.message}" + (f" _(proof: {'; '.join(m.proof_points)})_" if m.proof_points else "")
                for m in self.key_messages]
        out.append("### Tagline options\n" + "\n".join(f"- {t}" for t in self.taglines))
        out.append(f"**Say:** {', '.join(self.words_to_use) or '—'}  \n**Avoid:** {', '.join(self.words_to_avoid) or '—'}")
        out.append(f"**Visual direction:** {self.visual_direction}")
        if self.do_and_dont:
            out.append("### Do and don't\n" + "\n".join(f"- {d}" for d in self.do_and_dont))
        return "\n\n".join(out)


def _proof_figures(out: PositioningGuide, state: RunState, ctx: AgentContext) -> list[Issue]:
    """Any figure at all in a message, proof point or tagline ("trusted by 500 families", "rated 4.9") must come
    from the inputs: positioning copy gets reused everywhere, so an invented claim spreads."""
    known = _nums(" ".join(state.corpus + [state.user_message]))
    texts = [o for o in (out.value_proposition, out.elevator_pitch, *out.taglines,
                         *(p for m in out.key_messages for p in (m.message, *m.proof_points)))]
    bad = sorted({n for t in texts for n in _nums(t) if n not in known})
    if bad:
        return [Issue("error", "These figures aren't in the profile or anything the user said: " + ", ".join(bad[:6])
                      + ". Remove them or use a placeholder like [ADD PROOF].")]
    return []


POSITIONING_STRATEGIST = AgentSpec(
    name="business.positioning_strategist", kind="primary", products=BUSINESS,
    purpose="define this business's positioning, brand identity and messaging in plain language.",
    instructions=RULES + """
Call get_profile and search_context first. Base the positioning on the real differentiators and customers. Proof
points must be facts already in the profile or said by the user (no invented awards, years or numbers). Describe
visual direction in words; you don't create logos or images.
""",
    output_model=PositioningGuide, tools=READ_TOOLS, saves_as="positioning", max_tokens=3500,
    validators=(no_action_claims, _proof_figures,
                no_invented_numbers(lambda o: [o.value_proposition, o.elevator_pitch, *o.taglines,
                                               *(p for m in o.key_messages for p in [m.message, *m.proof_points])])))


# ====================================================================== 3. market, customer & competitor analysis
class Insight(Strict):
    point: str = Field(max_length=400)
    basis: str = Field(description="profile:… or doc:… ref you read, a search result URL, or user_message")


class CompetitorRow(Strict):
    competitor: str = Field(max_length=120)
    positioning: str = Field(max_length=300)
    strengths: list[Insight] = Field(default_factory=list, max_length=4)
    weaknesses: list[Insight] = Field(default_factory=list, max_length=4)
    opportunity_for_us: str = Field(max_length=300)


class MarketAnalysis(PrimaryOutput):
    focus: Literal["market", "competitors"]
    sources_used: str = Field(max_length=400, description="Plainly what this is based on, incl. whether any live research happened")
    market_insights: list[Insight] = Field(default_factory=list, max_length=8)
    customer_insights: list[Insight] = Field(default_factory=list, max_length=8)
    competitors: list[CompetitorRow] = Field(default_factory=list, max_length=6)
    questions_to_validate: list[str] = Field(min_length=1, max_length=6, description="How to check this with real customers")
    recommendations: list[str] = Field(min_length=1, max_length=6)

    def render(self) -> str:
        out = [f"_Based on: {self.sources_used}_"]
        if self.market_insights:
            out.append("### Market\n" + "\n".join(f"- {i.point}" for i in self.market_insights))
        if self.customer_insights:
            out.append("### Customers\n" + "\n".join(f"- {i.point}" for i in self.customer_insights))
        for c in self.competitors:
            out.append(f"### {c.competitor}\n{c.positioning}\n"
                       + "".join(f"\n- Strength: {s.point}" for s in c.strengths)
                       + "".join(f"\n- Weakness: {w.point}" for w in c.weaknesses)
                       + f"\n\n**Your opportunity:** {c.opportunity_for_us}")
        out.append("### Check with real customers\n" + "\n".join(f"- {q}" for q in self.questions_to_validate))
        out.append("### Recommendations\n" + "\n".join(f"- {r}" for r in self.recommendations))
        return "\n\n".join(out)


def _analysis_checks(out: MarketAnalysis, state: RunState, ctx: AgentContext) -> list[Issue]:
    issues = []
    want = _requested(r"^Focus:\s*(market|competitors)\s*$", state)
    if want and out.focus != want:
        issues.append(Issue("error", f"The user asked for a {want} analysis; set focus to {want}."))
    points = [*out.market_insights, *out.customer_insights,
              *(i for c in out.competitors for i in (*c.strengths, *c.weaknesses))]
    bad = [p.point for p in points if not _basis_ok(p.basis, state)]
    if bad:
        issues.append(Issue("error", "Every insight needs a real basis (a ref you read, a search URL, or "
                                     "user_message). Unsupported: " + "; ".join(bad[:3])))
    issues += _named_competitors_only([c.competitor for c in out.competitors], state)
    if out.focus == "competitors" and not out.competitors:
        issues.append(Issue("error", "A competitor analysis needs at least one named competitor; if none are known, "
                                     "say so in uncertainties and use focus market."))
    if not state.urls_seen and re.search(r"\b(web|online|live|internet) (research|search|data)\b", out.sources_used, re.I) \
            and not re.search(r"\bno\b|\bnot\b|without", out.sources_used, re.I):
        issues.append(Issue("error", "No live research happened in this run; don't say it did."))
    return issues


MARKET_ANALYST = AgentSpec(
    name="business.market_analyst", kind="primary", products=BUSINESS,
    purpose="analyse this business's market, customers or competitors using only information that's actually available.",
    instructions=RULES + """
Call get_profile and search_context (uploaded research, notes). Every insight cites its basis. You can't see market
data, competitors' accounts, prices or ads unless the user or a document provided them, so say what needs checking
and suggest simple ways to validate with real customers. State plainly in sources_used whether live web research
was involved (normally it isn't).
""",
    output_model=MarketAnalysis, tools=READ_TOOLS, saves_as="research", max_tokens=4500,
    validators=(no_action_claims, _analysis_checks,
                no_invented_numbers(lambda o: [i.point for i in (*o.market_insights, *o.customer_insights)]
                                    + [o.opportunity_for_us for o in o.competitors] + list(o.recommendations))))


# ====================================================================== 4. marketing plan generator
class Objective(Strict):
    objective: str = Field(max_length=200)
    metric: str = Field(max_length=120)
    target: str = Field(max_length=80, description="Owner's own target, or [TARGET] if they haven't set one")


class ChannelPlan(Strict):
    channel: Channel
    role: str = Field(max_length=200, description="What this channel does in the plan")
    tactics: list[str] = Field(min_length=1, max_length=5)
    effort: Effort
    budget_share: str = Field(max_length=120, description="Share of the stated budget, or 'no paid budget'")


class PlanPeriod(Strict):
    period: str = Field(max_length=40, description="e.g. Month 1")
    focus: str = Field(max_length=200)
    actions: list[str] = Field(min_length=1, max_length=6)


class PlanKpi(Strict):
    metric: str = Field(max_length=120)
    how_to_measure: str = Field(max_length=300)


class MarketingPlan(PrimaryOutput):
    executive_summary: str = Field(max_length=900)
    plan_months: int = Field(ge=1, le=12)
    objectives: list[Objective] = Field(min_length=1, max_length=5)
    target_segments: list[str] = Field(min_length=1, max_length=4)
    channel_plan: list[ChannelPlan] = Field(min_length=1, max_length=8)
    timeline: list[PlanPeriod] = Field(min_length=1, max_length=12)
    budget: str = Field(max_length=800, description="How to split the stated budget; amounts only from the profile")
    kpis: list[PlanKpi] = Field(min_length=1, max_length=8)
    risks: list[str] = Field(default_factory=list, max_length=5)

    def render(self) -> str:
        out = [self.executive_summary, "### Objectives"]
        out += [f"- {o.objective}: {o.metric}, target {o.target}" for o in self.objectives]
        out.append(f"**For:** {', '.join(self.target_segments)}")
        out.append("### Channels\n| Channel | Role | Effort | Budget |\n|---|---|---|---|\n"
                   + "\n".join(f"| {c.channel} | {c.role} | {c.effort} | {c.budget_share} |" for c in self.channel_plan))
        out.append("### Timeline\n" + "\n".join(f"- **{p.period}** ({p.focus}): " + "; ".join(p.actions) for p in self.timeline))
        out.append(f"**Budget:** {self.budget}")
        out.append("**Measure:** " + "; ".join(f"{k.metric} ({k.how_to_measure})" for k in self.kpis))
        if self.risks:
            out.append("**Risks:** " + "; ".join(self.risks))
        return "\n\n".join(out)


def _plan_checks(out: MarketingPlan, state: RunState, ctx: AgentContext) -> list[Issue]:
    issues = []
    want = _requested(r"^Plan length:\s*(\d+)\s*months?\s*$", state)
    if want and out.plan_months != int(want):
        issues.append(Issue("error", f"The plan must cover exactly {want} months."))
    if len(out.timeline) != out.plan_months:
        issues.append(Issue("error", f"Give one timeline entry per month ({out.plan_months})."))
    return issues


MARKETING_PLANNER = AgentSpec(
    name="business.marketing_planner", kind="primary", products=BUSINESS,
    purpose="create a practical marketing plan for this business's goals, stage, market and budget.",
    instructions=RULES + """
Call get_profile and search_context first. Pick a small number of channels the business can actually run with its
budget and team; explain the role of each. Objectives use the owner's targets or [TARGET]. Split only the budget
the owner gave (or say 'no paid budget'). One timeline entry per month of the plan.
""",
    output_model=MarketingPlan, tools=READ_TOOLS, saves_as="marketing_plan", max_tokens=6000,
    validators=(no_action_claims, _plan_checks,
                no_invented_numbers(lambda o: [o.executive_summary, o.budget, *(x.target for x in o.objectives),
                                               *(c.budget_share for c in o.channel_plan)])))


# ====================================================================== 5. advertising & campaign planning
class AdPlatform(Strict):
    channel: AdChannel
    why: str = Field(max_length=300)
    audience_targeting: str = Field(max_length=400, description="Who to target, in the platform's terms where known")
    formats: list[str] = Field(min_length=1, max_length=4)
    budget_note: str = Field(max_length=200)


class AdCreative(Strict):
    channel: AdChannel
    headline: str = Field(max_length=90)
    primary_text: str = Field(max_length=500)
    call_to_action: str = Field(max_length=40)


class AdPlan(PrimaryOutput):
    objective: str = Field(max_length=300)
    readiness_note: str = Field(max_length=400, description="Is paid advertising sensible now for this business? Why?")
    start_date: str
    end_date: str
    platforms: list[AdPlatform] = Field(min_length=1, max_length=4)
    creatives: list[AdCreative] = Field(min_length=1, max_length=8)
    test_plan: str = Field(max_length=500)
    measurement: list[str] = Field(min_length=1, max_length=6)
    compliance_notes: list[str] = Field(default_factory=list, max_length=5)

    def render(self) -> str:
        out = [f"**Objective:** {self.objective}", f"_{self.readiness_note}_", f"**When:** {self.start_date} to {self.end_date}"]
        for p in self.platforms:
            out.append(f"### {p.channel}\n{p.why}\n- **Target:** {p.audience_targeting}\n- **Formats:** "
                       f"{', '.join(p.formats)}\n- **Budget:** {p.budget_note}")
        out.append("### Ad copy\n" + "\n".join(f"- **{c.channel}** · {c.headline}\n  > {c.primary_text}\n  CTA: {c.call_to_action}"
                                               for c in self.creatives))
        out.append(f"**Test:** {self.test_plan}")
        out.append("**Measure:** " + "; ".join(self.measurement))
        if self.compliance_notes:
            out.append("**Check before launching:** " + "; ".join(self.compliance_notes))
        return "\n\n".join(out)


def _ads_checks(out: AdPlan, state: RunState, ctx: AgentContext) -> list[Issue]:
    issues = []
    s, e = _parse_date(out.start_date), _parse_date(out.end_date)
    if not s or not e or s > e:
        return [Issue("error", "start_date and end_date must be valid YYYY-MM-DD dates in order.")]
    want = requested_range(state)
    if want and (s, e) != want:
        issues.append(Issue("error", f"The campaign must run exactly {want[0]} to {want[1]}."))
    stray = {c.channel for c in out.creatives} - {p.channel for p in out.platforms}
    if stray:
        issues.append(Issue("error", f"Ad copy for platforms not in the plan: {', '.join(sorted(stray))}."))
    return issues


ADS_PLANNER = AgentSpec(
    name="business.ads_planner", kind="primary", products=BUSINESS,
    purpose="plan paid advertising for this business: whether it's sensible now, where, who to target, ad copy and how to test.",
    instructions=RULES + """
Call get_profile first. Say honestly in readiness_note if paid ads aren't sensible yet (e.g. idea stage, no budget,
nothing to measure). Use only the budget the owner gave. Ad copy must not claim results, prices, discounts or
awards that aren't in the profile. Platform targeting options and policies change: add compliance_notes for
anything the owner must check in the ad platform before launching. You can't launch or pay for ads.
""",
    output_model=AdPlan, tools=READ_TOOLS, saves_as="ad_plan", max_tokens=4500,
    validators=(no_action_claims, _ads_checks,
                no_invented_numbers(lambda o: [*(c.headline for c in o.creatives), *(c.primary_text for c in o.creatives),
                                               *(p.budget_note for p in o.platforms)])))


# ====================================================================== 6. acquisition & retention
class Tactic(Strict):
    name: str = Field(max_length=100)
    channel: Channel
    how_it_works: str = Field(max_length=400)
    steps: list[str] = Field(min_length=1, max_length=6)
    effort: Effort
    cost_note: str = Field(max_length=200)
    metric: str = Field(max_length=120)


class JourneyStage(Strict):
    stage: str = Field(max_length=60)
    goal: str = Field(max_length=200)


class GrowthPlan(PrimaryOutput):
    focus: Literal["acquisition", "retention"]
    summary: str = Field(max_length=700)
    journey: list[JourneyStage] = Field(min_length=2, max_length=6)
    tactics: list[Tactic] = Field(min_length=2, max_length=8)
    offers_or_hooks: list[str] = Field(default_factory=list, max_length=5)
    quick_wins: list[str] = Field(min_length=1, max_length=5, description="Things to do this week")
    measurement: list[str] = Field(min_length=1, max_length=5)

    def render(self) -> str:
        out = [self.summary, "**Journey:** " + " → ".join(f"{j.stage} ({j.goal})" for j in self.journey)]
        for t in self.tactics:
            out.append(f"### {t.name} · {t.channel} · {t.effort} effort\n{t.how_it_works}\n"
                       + "\n".join(f"{i}. {s}" for i, s in enumerate(t.steps, 1))
                       + f"\n\n_Cost:_ {t.cost_note} · _Measure:_ {t.metric}")
        if self.offers_or_hooks:
            out.append("### Offer ideas\n" + "\n".join(f"- {o}" for o in self.offers_or_hooks))
        out.append("### Quick wins this week\n" + "\n".join(f"- {q}" for q in self.quick_wins))
        return "\n\n".join(out)


def _growth_checks(out: GrowthPlan, state: RunState, ctx: AgentContext) -> list[Issue]:
    want = _requested(r"^Focus:\s*(acquisition|retention)\s*$", state)
    return [Issue("error", f"The user asked for a {want} plan; set focus to {want}.")] if want and out.focus != want else []


GROWTH_STRATEGIST = AgentSpec(
    name="business.growth_strategist", kind="primary", products=BUSINESS,
    purpose="plan lead generation and customer acquisition, or customer retention, for how this business's customers actually buy.",
    instructions=RULES + """
Call get_profile and search_context first. Acquisition: how strangers become leads and customers (e.g. referral
schemes, partnerships, local listings, outreach, lead magnets). Retention: how customers come back and refer
others (follow-ups, loyalty, win-back, service). Match the business model (B2B vs B2C), category and stage. Offers
must not promise discounts or prices the owner hasn't set: use [YOUR OFFER].
""",
    output_model=GrowthPlan, tools=READ_TOOLS, saves_as="growth_plan", max_tokens=4500,
    validators=(no_action_claims, _growth_checks,
                no_invented_numbers(lambda o: [o.summary, *o.offers_or_hooks, *o.quick_wins,
                                               *(t.cost_note for t in o.tactics), *(t.how_it_works for t in o.tactics)])))


# ====================================================================== 7. performance analysis
class Finding(Strict):
    point: str = Field(max_length=400)
    metric_basis: str = Field(max_length=200)


class PerformanceAnalysis(AgentOutput):
    headline: str = Field(max_length=300)
    what_worked: list[Finding] = Field(default_factory=list, max_length=6)
    what_to_improve: list[str] = Field(default_factory=list, max_length=6)
    budget_shifts: list[str] = Field(default_factory=list, max_length=4, description="Where to move spend, if the data supports it")
    next_actions: list[str] = Field(min_length=1, max_length=6)
    data_caveats: list[str] = Field(min_length=1, max_length=5)

    def render(self) -> str:
        out = [f"**{self.headline}**", *(f"- {f.point}" for f in self.what_worked)]
        if self.what_to_improve:
            out.append("**Improve:**\n" + "\n".join(f"- {w}" for w in self.what_to_improve))
        if self.budget_shifts:
            out.append("**Budget:**\n" + "\n".join(f"- {b}" for b in self.budget_shifts))
        out.append("**Next:**\n" + "\n".join(f"- {n}" for n in self.next_actions))
        out.append("_About this data: " + " ".join(self.data_caveats) + "_")
        return "\n\n".join(out)


def _perf_numbers(out: PerformanceAnalysis, state: RunState, ctx: AgentContext) -> list[Issue]:
    return strict_numbers([out.headline, *(f.point for f in out.what_worked), *out.what_to_improve,
                           *out.budget_shifts, *out.next_actions], state)


PERFORMANCE_ANALYST = AgentSpec(
    name="business.performance_analyst", kind="primary", products=BUSINESS,
    purpose="explain this business's recorded marketing results in plain words and recommend what to change.",
    instructions="""
The task contains results calculated by the system from rows the team recorded. Use only those figures: no
estimates, no industry benchmarks. Compare channels on cost per lead, cost per customer and return on spend only
where those were recorded. Suggest budget shifts only if the data supports them, and always include caveats
(who entered it, missing figures, small numbers, mixed currencies).
""",
    output_model=PerformanceAnalysis, tools=("get_profile", "search_context"), saves_as="report", max_tokens=2500,
    validators=(no_action_claims, _perf_numbers))


BUSINESS_AGENTS = (PROFILE_BUILDER, POSITIONING_STRATEGIST, MARKET_ANALYST, MARKETING_PLANNER, ADS_PLANNER,
                   GROWTH_STRATEGIST, PERFORMANCE_ANALYST)
