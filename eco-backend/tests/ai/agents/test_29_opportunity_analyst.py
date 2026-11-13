"""Agent 29: freelancer.opportunity_analyst. Uses computed eligibility/red flags; matches cite the profile."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.freelancer import OPPORTUNITY_ANALYST
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final
from tests.freelancer.helpers import fl_ws


def msg(elig="eligible", flags="none"):
    return f"Check this opportunity\nEligibility (computed): {elig}\nTime-zone overlap (computed): 5.0 hours\nRed flags (computed): {flags}"


def analysis(rec="apply_after_checks", reqs=None, elig_comment="The listing names EMEA, which includes Nigeria."):
    return final({"summary": "The listing asks for a UI designer for a payments app.",
                  "requirements": reqs or [{"requirement": "Figma", "met": "yes", "profile_ref": "profile:skills[0]"},
                                           {"requirement": "3 years experience", "met": "no", "profile_ref": None}],
                  "strengths_to_lead_with": [{"point": "Onboarding redesign case study", "profile_ref": "profile:portfolio[0]"}],
                  "gaps": ["Years of experience"], "eligibility_comment": elig_comment,
                  "timezone_comment": "About 5 hours of overlap.", "red_flags": [],
                  "verify_before_applying": ["The posting is live on the company's own site"],
                  "recommendation": rec, "recommendation_reason": "Strong portfolio fit, but check the experience bar.",
                  "application_angle": "Lead with the onboarding case study.", "uncertainties": [], "warnings": [],
                  "memory_candidates": []})


async def _run(agent_ctx, a, ws, p, m):
    async with agent_ctx(a, ws, provider=p) as ctx:
        return await run_agent(OPPORTUNITY_ANALYST, ctx, RunState(m), [LLMMessage("user", m)])


async def test_analysis(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    out = await _run(agent_ctx, a, ws, ScriptedProvider().on("freelancer.opportunity_analyst", call("get_profile", {}), analysis()), msg())
    assert "Apply after the checks below" in out.render() and "◐" not in out.render()


async def test_respects_computed_checks(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    bad = analysis(rec="apply", reqs=[{"requirement": "Python", "met": "yes", "profile_ref": "profile:skills[7]"}],
                   elig_comment="Looks fine.")
    p = ScriptedProvider().on("freelancer.opportunity_analyst", call("get_profile", {}), bad, bad)
    with pytest.raises(AgentError):
        await _run(agent_ctx, a, ws, p, msg("not_eligible", "upfront_fee"))
    m = p.sent_to("freelancer.opportunity_analyst")[2].messages[-1].content
    assert "must cite a profile ref" in m and "rule out a plain 'apply'" in m and "not_eligible: say so" in m
