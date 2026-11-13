"""Agent 11: creator.research_analyst. Insights must cite a real basis; no invented competitors or web research."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.creator import RESEARCH_ANALYST
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final


def report(audience=None, competitors=None, sources="Your profile and competitor notes; no live web research."):
    return final({"scope": "Audience and two competitors", "sources_used": sources,
                  "audience_insights": audience if audience is not None else [
                      {"point": "Audience is professionals on the Island", "basis": "profile:audience"}],
                  "competitor_insights": competitors if competitors is not None else [
                      {"competitor": "Bean Bar", "observations": [
                          {"point": "Posts mostly product photos", "basis": "profile:competitors[0]"}],
                       "opportunities": ["Show the people behind the coffee"]}],
                  "content_gaps": ["No behind-the-scenes content"], "recommended_actions": ["Start a weekly roast reel"],
                  "uncertainties": [], "warnings": [], "memory_candidates": []})


async def _setup(client, a, ws):
    r = await client.put(f"/v1/workspaces/{ws}/client-account", headers=a.h, json={
        "client_name": "Lagos Coffee Co.", "audience": {"summary": "Professionals on the Island"},
        "competitors": [{"name": "Bean Bar", "handle": "@beanbar", "platform": "instagram",
                         "notes": "Mostly product photos"}]})
    assert r.status_code == 200, r.text


async def _run(agent_ctx, a, ws, p):
    async with agent_ctx(a, ws, provider=p) as ctx:
        st = RunState("Analyse our audience and competitors")
        return await run_agent(RESEARCH_ANALYST, ctx, st, [LLMMessage("user", "## User request\n" + st.user_message)])


async def test_grounded_report(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    await _setup(client, a, ws)
    p = ScriptedProvider().on("creator.research_analyst", call("get_profile", {}), report())
    out = await _run(agent_ctx, a, ws, p)
    assert "### Bean Bar" in out.render() and "no live web research" in out.render()


async def test_invented_competitor_basis_and_fake_research(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    await _setup(client, a, ws)
    bad = report(competitors=[{"competitor": "Starbucks", "observations": [
        {"point": "Has 2M followers", "basis": "https://instagram.com/starbucks"}], "opportunities": []}],
        sources="Live web research of competitor accounts")
    p = ScriptedProvider().on("creator.research_analyst", call("get_profile", {}), bad, bad)
    with pytest.raises(AgentError):
        await _run(agent_ctx, a, ws, p)
    msg = p.sent_to("creator.research_analyst")[2].messages[-1].content
    assert "Starbucks" in msg and "Unsupported" in msg and "No web research was done" in msg
