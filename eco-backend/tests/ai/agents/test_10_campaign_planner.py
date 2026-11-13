"""Agent 10: creator.campaign_planner."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.creator import CAMPAIGN_PLANNER
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, final

REQ = "Plan a cold brew launch campaign.\nDate range: 2027-01-05 to 2027-02-05"


def campaign(phases=None, channels=("instagram", "x"), budget="[YOUR BUDGET] for boosted posts", start="2027-01-05"):
    return final({
        "name": "Cold Brew Launch", "objective": "Get regulars to try cold brew", "audience": "Island professionals",
        "key_message": "Your calm, now iced.", "start_date": start, "end_date": "2027-02-05",
        "channels": list(channels),
        "phases": phases or [{"name": "Tease", "start_date": "2027-01-05", "end_date": "2027-01-12",
                              "goal": "Build curiosity", "activities": ["Countdown stories"],
                              "deliverables": [{"platform": "instagram", "format": "story", "description": "Countdown"}]}],
        "kpis": [{"metric": "Cold brew orders per week", "how_to_measure": "Till receipts"}],
        "budget_note": budget, "risks": ["Rainy season"], "uncertainties": [], "warnings": [], "memory_candidates": []})


async def _run(agent_ctx, a, ws, p):
    async with agent_ctx(a, ws, provider=p) as ctx:
        return await run_agent(CAMPAIGN_PLANNER, ctx, RunState(REQ), [LLMMessage("user", "## User request\n" + REQ)])


async def test_valid_campaign(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    out = await _run(agent_ctx, a, ws, ScriptedProvider().on("creator.campaign_planner", campaign()))
    assert out.phases[0].name == "Tease" and "### Tease (2027-01-05 to 2027-01-12)" in out.render()


async def test_phase_dates_channels_and_prices(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    outside = [{"name": "Sustain", "start_date": "2027-02-01", "end_date": "2027-03-01", "goal": "Keep it going",
                "activities": [], "deliverables": [{"platform": "tiktok", "format": "video", "description": "x"}]}]
    p = ScriptedProvider().on("creator.campaign_planner", campaign(phases=outside, budget="About ₦300,000"),
                              campaign(start="2027-01-06"))
    with pytest.raises(AgentError):
        await _run(agent_ctx, a, ws, p)
    msg = p.sent_to("creator.campaign_planner")[1].messages[-1].content
    assert "inside the campaign dates" in msg and "tiktok" in msg and "₦300,000" in msg
