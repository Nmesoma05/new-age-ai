"""Agent 15: business.market_analyst (market, customer and competitor analysis)."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.business import MARKET_ANALYST
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final
from tests.business.helpers import biz_ws


def analysis(focus="competitors", competitors=None, sources="Your profile notes; no live web research."):
    return final({"focus": focus, "sources_used": sources, "market_insights": [],
                  "customer_insights": [{"point": "Hosts care most about punctuality", "basis": "user_message"}],
                  "competitors": competitors if competitors is not None else [
                      {"competitor": "Chop Express", "positioning": "Low price",
                       "strengths": [{"point": "Cheaper", "basis": "profile:competitors[0]"}],
                       "weaknesses": [{"point": "Often late", "basis": "profile:competitors[0]"}],
                       "opportunity_for_us": "Guarantee delivery times"}],
                  "questions_to_validate": ["Ask five recent hosts what nearly made them choose someone else"],
                  "recommendations": ["Advertise the delivery promise"], "uncertainties": [], "warnings": [],
                  "memory_candidates": []})


async def _run(agent_ctx, a, ws, p, msg):
    async with agent_ctx(a, ws, provider=p) as ctx:
        st = RunState(msg)
        return await run_agent(MARKET_ANALYST, ctx, st, [LLMMessage("user", "## User request\n" + msg)])


async def test_grounded_competitor_analysis(client, signup, make_workspace, agent_ctx):
    a, ws = await biz_ws(client, signup, make_workspace)
    p = ScriptedProvider().on("business.market_analyst", call("get_profile", {}), analysis())
    out = await _run(agent_ctx, a, ws, p, "Hosts care most about punctuality. Compare us with competitors.\nFocus: competitors")
    assert out.competitors[0].competitor == "Chop Express" and "**Your opportunity:**" in out.render()


async def test_wrong_focus_unsupported_basis_and_fake_research(client, signup, make_workspace, agent_ctx):
    a, ws = await biz_ws(client, signup, make_workspace)
    bad = analysis(focus="market", competitors=[{"competitor": "Chop Express", "positioning": "x",
                   "strengths": [{"point": "Has 40 branches", "basis": "https://example.com/made-up"}], "weaknesses": [],
                   "opportunity_for_us": "y"}], sources="Live web research")
    p = ScriptedProvider().on("business.market_analyst", call("get_profile", {}), bad, bad)
    with pytest.raises(AgentError):
        await _run(agent_ctx, a, ws, p, "Compare us with competitors\nFocus: competitors")
    msg = p.sent_to("business.market_analyst")[2].messages[-1].content
    assert "set focus to competitors" in msg and "Has 40 branches" in msg and "No live research" in msg
