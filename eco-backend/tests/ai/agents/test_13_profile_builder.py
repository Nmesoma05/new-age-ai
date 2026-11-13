"""Agent 13: business.profile_builder (Marketing Intelligence Profile)."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.business import PROFILE_BUILDER
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final
from tests.business.helpers import biz_ws


def profile(**kw):
    base = {"summary": "A home-style catering business in Awka selling party trays to families and planners.",
            "stage_assessment": "New: first regular customers, growing by word of mouth.",
            "positioning_statement": "Home-cooked party food delivered the same day in Awka.",
            "value_proposition": "Reliable, tasty party food without the stress.",
            "customer_segments": [{"name": "Party hosts", "description": "Families hosting birthdays and naming ceremonies",
                                   "needs": ["on-time delivery"], "buying_triggers": ["upcoming event"],
                                   "where_to_reach": ["whatsapp", "instagram"]}],
            "competitive_landscape": [{"competitor": "Chop Express", "what_we_know": "Cheaper but often late",
                                       "how_to_stand_out": "Promise and prove on-time delivery"}],
            "channel_fit": [{"channel": "whatsapp", "fit": "strong", "why": "Customers already order there"},
                            {"channel": "google_business_profile", "fit": "possible", "why": "Local search"}],
            "priorities": ["Collect reviews from every order"], "risks": [], "data_gaps": ["Average order frequency"],
            "uncertainties": [], "warnings": [], "memory_candidates": []}
    base.update(kw)
    return final(base)


async def _run(agent_ctx, a, ws, p):
    async with agent_ctx(a, ws, provider=p) as ctx:
        return await run_agent(PROFILE_BUILDER, ctx, RunState("Build my profile"),
                               [LLMMessage("user", "## User request\nBuild my profile")])


async def test_builds_from_profile(client, signup, make_workspace, agent_ctx):
    a, ws = await biz_ws(client, signup, make_workspace)
    p = ScriptedProvider().on("business.profile_builder", call("get_profile", {}), profile())
    out = await _run(agent_ctx, a, ws, p)
    assert out.channel_fit[0].channel == "whatsapp" and "### Channel fit" in out.render()
    seen = p.sent_to("business.profile_builder")[1].messages[-1].content
    assert "food_hospitality" in seen and "NGN" in seen  # the profile, incl. category and budget, reached the model


async def test_invented_competitor_and_stats_rejected(client, signup, make_workspace, agent_ctx):
    a, ws = await biz_ws(client, signup, make_workspace)
    bad = profile(competitive_landscape=[{"competitor": "Domino's", "what_we_know": "x", "how_to_stand_out": "y"}],
                  summary="Awka's catering market grows 18% a year.")
    p = ScriptedProvider().on("business.profile_builder", call("get_profile", {}), bad, bad)
    with pytest.raises(AgentError) as e:
        await _run(agent_ctx, a, ws, p)
    assert e.value.code == "output_invalid"
    msg = p.sent_to("business.profile_builder")[2].messages[-1].content
    assert "Domino's" in msg and "18%" in msg
