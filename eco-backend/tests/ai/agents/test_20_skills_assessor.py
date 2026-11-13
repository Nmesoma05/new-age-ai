"""Agent 20: freelancer.skills_assessor. Evidence vs claims vs suggestions."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.freelancer import SKILLS_ASSESSOR
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final
from tests.freelancer.helpers import fl_ws


def assessment(skills, summary="Early-career UI designer with one internship and a solid case study."):
    return final({"summary": summary, "stage_read": "Skilled, building first client work.", "skills": skills,
                  "strengths": ["Clear onboarding design"], "gaps": [{"gap": "Paid client work", "why_it_matters": "Proof",
                  "how_to_close": "One small paid project"}], "suggested_directions": [{"title": "Fintech onboarding audits",
                  "kind": "service", "why": "Matches your case study"}], "headline_options": ["UI/UX designer for fintech apps"],
                  "missing_information": [], "uncertainties": [], "warnings": [], "memory_candidates": []})


GOOD = [{"skill": "Figma", "evidence_level": "shown", "evidence_refs": ["profile:portfolio[0]", "profile:skills[0]"], "note": "Used in your case study"},
        {"skill": "Webflow", "evidence_level": "stated", "evidence_refs": ["profile:skills[2]"], "note": "Listed, no project yet"},
        {"skill": "Prototyping", "evidence_level": "suggested", "evidence_refs": [], "note": "Worth adding"}]


async def _run(agent_ctx, a, ws, p):
    async with agent_ctx(a, ws, provider=p) as ctx:
        return await run_agent(SKILLS_ASSESSOR, ctx, RunState("Assess my skills"), [LLMMessage("user", "Assess my skills")])


async def test_evidence_levels(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    out = await _run(agent_ctx, a, ws, ScriptedProvider().on("freelancer.skills_assessor", call("get_profile", {}), assessment(GOOD)))
    md = out.render()
    assert "✓ shown in your work" in md and "listed by you" in md and "suggestion: to learn" in md


async def test_overclaiming_rejected(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    bad = assessment([{"skill": "Webflow", "evidence_level": "shown", "evidence_refs": ["profile:skills[2]"], "note": "x"},
                      {"skill": "React", "evidence_level": "stated", "evidence_refs": ["profile:skills[9]"], "note": "x"},
                      {"skill": "SQL", "evidence_level": "suggested", "evidence_refs": ["profile:skills[0]"], "note": "x"}],
                     summary="Designer with 5 years of experience.")
    p = ScriptedProvider().on("freelancer.skills_assessor", call("get_profile", {}), bad, bad)
    with pytest.raises(AgentError):
        await _run(agent_ctx, a, ws, p)
    msg = p.sent_to("freelancer.skills_assessor")[2].messages[-1].content
    assert "that's 'stated', not 'shown'" in msg and "profile:skills[9]" in msg and "can't cite evidence" in msg and "5" in msg
