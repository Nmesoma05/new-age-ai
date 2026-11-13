"""Agent 22: freelancer.interview_coach. Stories only from real experience."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.freelancer import INTERVIEW_COACH
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final
from tests.freelancer.helpers import fl_ws

MSG = "Prepare me for a product designer interview\nQuestion count: 3"


def q(text, ref=None, t="behavioural"):
    return {"question": text, "type": t, "why_asked": "To see how you work", "answer_outline": "Use the onboarding story",
            "story_ref": ref}


def prep(questions, stories=None):
    return final({"role": "Product designer", "company_notes": [], "questions": questions,
                  "stories": stories if stories is not None else [{"title": "Onboarding redesign", "situation": "A savings app lost users at sign-up",
                               "task": "Simplify onboarding", "action": "Mapped the flow and cut steps",
                               "result": "Cut onboarding from 7 screens to 4", "source_ref": "profile:portfolio[0]"}],
                  "questions_to_ask": ["How does design work with engineering?"],
                  "logistics": ["Interview is likely in the employer's time zone: confirm the time in Africa/Lagos"],
                  "missing_information": [], "uncertainties": [], "warnings": [], "memory_candidates": []})


async def _run(agent_ctx, a, ws, p):
    async with agent_ctx(a, ws, provider=p) as ctx:
        return await run_agent(INTERVIEW_COACH, ctx, RunState(MSG), [LLMMessage("user", MSG)])


async def test_prep(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    good = prep([q("Tell me about a design you improved", "profile:portfolio[0]"), q("Why fintech?", t="motivation"),
                 q("What are your pay expectations?", t="pay_and_logistics")])
    out = await _run(agent_ctx, a, ws, ScriptedProvider().on("freelancer.interview_coach", call("get_profile", {}), good))
    assert "### Your stories (STAR)" in out.render() and len(out.questions) == 3


async def test_invented_story_and_count(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    bad = prep([q("Tell me about leading a team", "profile:experiences[4]"), q("Why us?"), q("Strengths?"), q("Weakness?")],
               stories=[{"title": "Led a team", "situation": "At a bank", "task": "Lead 12 designers", "action": "Led",
                         "result": "Raised conversion by 40%", "source_ref": "profile:experiences[4]"}])
    p = ScriptedProvider().on("freelancer.interview_coach", call("get_profile", {}), bad, bad)
    with pytest.raises(AgentError):
        await _run(agent_ctx, a, ws, p)
    msg = p.sent_to("freelancer.interview_coach")[2].messages[-1].content
    assert "refs you didn't read" in msg and "give exactly 3" in msg and "12" in msg and "40" in msg
