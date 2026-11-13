"""Agent 28: freelancer.learning_planner. Exact week count; links only from the checked directory."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.freelancer import LEARNING_PLANNER
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final
from tests.freelancer.helpers import fl_ws

MSG = "Plan my learning to become a product designer\nWeeks: 3\nHours per week: 6"


def plan(weeks):
    return final({"goal": "Junior product designer roles", "starting_point": "Figma intermediate, research beginner",
                  "weeks": weeks, "milestones": ["Second case study"], "portfolio_outputs": ["Design-system mini kit"],
                  "missing_information": [], "uncertainties": [], "warnings": [], "memory_candidates": []})


def wk(n, url=None):
    return {"week": n, "focus": f"Focus {n}", "activities": ["Practise"],
            "resources": [{"name": "ALX Africa", "url": url, "cost": "unknown"}] if url is not False else [],
            "output": "A small piece"}


async def _run(agent_ctx, a, ws, p):
    async with agent_ctx(a, ws, provider=p) as ctx:
        return await run_agent(LEARNING_PLANNER, ctx, RunState(MSG), [LLMMessage("user", MSG)])


async def test_plan(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    good = plan([wk(1, "https://www.alxafrica.com"), wk(2), wk(3)])
    out = await _run(agent_ctx, a, ws, ScriptedProvider().on("freelancer.learning_planner", call("get_profile", {}), good))
    assert "### Week 3" in out.render()


async def test_week_count_and_made_up_links(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    bad = plan([wk(1, "https://free-ux-course.example.com"), wk(2)])
    p = ScriptedProvider().on("freelancer.learning_planner", call("get_profile", {}), bad, bad)
    with pytest.raises(AgentError):
        await _run(agent_ctx, a, ws, p)
    msg = p.sent_to("freelancer.learning_planner")[2].messages[-1].content
    assert "exactly 3 weeks" in msg and "free-ux-course.example.com" in msg
