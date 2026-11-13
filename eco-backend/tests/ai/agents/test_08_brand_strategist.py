"""Agent 8: creator.brand_strategist."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.creator import BRAND_STRATEGIST
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final


def strategy(**kw):
    base = {"positioning": "Specialty coffee for busy Lagos professionals who want a calm start.",
            "voice_attributes": [{"trait": "Warm", "what_it_means": "Talks like a friendly barista", "avoid": "Gushing"},
                                 {"trait": "Witty", "what_it_means": "Light wordplay", "avoid": "Sarcasm"}],
            "tone_by_platform": [{"platform": "x", "guidance": "Short and punchy"}],
            "words_to_use": ["brew", "slow morning"], "words_to_avoid": ["cheap"],
            "sample_lines": ["Your calm starts here.", "Slow mornings, strong coffee."],
            "audience_personas": [{"name": "Busy professional", "description": "Works on the Island, orders on the go",
                                   "needs": ["speed"], "where_they_spend_time": ["instagram", "x"]}],
            "content_pillars": [{"name": "Craft", "purpose": "Show how coffee is made", "example_topics": ["roasting"]},
                                {"name": "Community", "purpose": "Customers and staff", "example_topics": ["regulars"]}],
            "uncertainties": [], "warnings": [], "memory_candidates": []}
    base.update(kw)
    return final(base)


async def _run(agent_ctx, a, ws, p):
    async with agent_ctx(a, ws, provider=p) as ctx:
        st = RunState("Build our brand voice")
        return await run_agent(BRAND_STRATEGIST, ctx, st, [LLMMessage("user", "## User request\nBuild our brand voice")]), st


async def test_builds_profile_from_context(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    p = ScriptedProvider().on("creator.brand_strategist", call("get_profile", {}), strategy())
    out, st = await _run(agent_ctx, a, ws, p)
    assert len(out.content_pillars) == 2 and "### Content pillars" in out.render()
    assert st.tool_logs[0].tool == "get_profile"


async def test_invented_audience_stats_rejected(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    bad = strategy(audience_personas=[{"name": "Gen Z", "description": "68% of buyers are under 25",
                                       "needs": [], "where_they_spend_time": ["tiktok"]}])
    p = ScriptedProvider().on("creator.brand_strategist", bad, bad)
    with pytest.raises(AgentError) as e:
        await _run(agent_ctx, a, ws, p)
    assert "68%" in e.value.message


async def test_needs_at_least_two_pillars(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    one = strategy(content_pillars=[{"name": "Craft", "purpose": "x", "example_topics": []}])
    p = ScriptedProvider().on("creator.brand_strategist", one, strategy())
    out, st = await _run(agent_ctx, a, ws, p)
    assert len(st.llm_calls) == 2 and len(out.content_pillars) == 2
