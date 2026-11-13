"""Agent 24: freelancer.portfolio_builder. No invented clients, results or testimonials."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.freelancer import PORTFOLIO_BUILDER
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final
from tests.freelancer.helpers import fl_ws

MSG = 'Write a case study for my savings app onboarding project. The founder said: "Our sign-ups finally make sense."'


def case(**kw):
    body = {"title": "Making savings-app onboarding simple", "project_ref": "profile:portfolio[0]",
            "client_label": "A Nigerian savings app", "summary": "Redesigned onboarding for a savings app.",
            "challenge": "Users dropped off during a long sign-up.", "approach": ["Mapped the flow", "Removed steps"],
            "my_role": "UI designer", "outcome": "Cut onboarding from 7 screens to 4. [ADD RESULT: sign-up rate]",
            "skills_used": ["Figma"], "testimonial": "Our sign-ups finally make sense.",
            "visuals_to_add": ["Before/after screens"], "missing_information": ["Sign-up rate before and after"],
            "uncertainties": [], "warnings": [], "memory_candidates": []}
    body.update(kw)
    return final(body)


async def _run(agent_ctx, a, ws, p):
    async with agent_ctx(a, ws, provider=p) as ctx:
        return await run_agent(PORTFOLIO_BUILDER, ctx, RunState(MSG), [LLMMessage("user", MSG)])


async def test_case_study(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    out = await _run(agent_ctx, a, ws, ScriptedProvider().on("freelancer.portfolio_builder", call("get_profile", {}), case()))
    assert "> Our sign-ups finally make sense." in out.render()


async def test_invented_client_result_quote(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    bad = case(client_label="PiggyVest", outcome="Conversion rose 62%.", testimonial="Chiamaka is the best designer we've hired.")
    p = ScriptedProvider().on("freelancer.portfolio_builder", call("get_profile", {}), bad, bad)
    with pytest.raises(AgentError):
        await _run(agent_ctx, a, ws, p)
    msg = p.sent_to("freelancer.portfolio_builder")[2].messages[-1].content
    assert "testimonial isn't a quote" in msg and "PiggyVest" in msg and "62" in msg
