"""Agent 7: shared.researcher. Findings must cite URLs actually returned this run; no research = says so."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.specs import RESEARCHER
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final
from tests.ai.test_tools import FakeResearch


def brief(findings, available=True, confidence="medium"):
    return final({"question": "Coffee trends in Lagos", "research_available": available, "findings": findings,
                  "gaps": [], "confidence": confidence, "uncertainties": [], "warnings": []})


async def _run(agent_ctx, a, ws, p, research):
    async with agent_ctx(a, ws, provider=p, research=research) as ctx:
        st = RunState("What's trending in coffee in Lagos?")
        return await run_agent(RESEARCHER, ctx, st, [LLMMessage("user", st.user_message)]), st


async def test_cites_only_returned_urls(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    search = call("web_search", {"query": "coffee trends Lagos", "max_results": 3})
    good = {"claim": "Cold brew sales rose", "source_url": "https://news.example/coffee", "source_title": "Coffee trends"}
    made_up = {"claim": "Lagos coffee market worth $2bn", "source_url": "https://madeup.example/x", "source_title": "X"}
    p = ScriptedProvider().on("shared.researcher", search, brief([good, made_up]), brief([good]))
    out, st = await _run(agent_ctx, a, ws, p, FakeResearch())
    assert [f.source_url for f in out.findings] == ["https://news.example/coffee"]
    assert "madeup.example" in p.sent_to("shared.researcher")[2].messages[-1].content


async def test_unavailable_research_is_reported_not_faked(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    search = call("web_search", {"query": "coffee trends Lagos", "max_results": 3})
    from_memory = {"claim": "Cold brew is popular", "source_url": "https://news.example/coffee", "source_title": "t"}
    p = ScriptedProvider().on("shared.researcher", search, brief([from_memory]), brief([], available=False,
                                                                                        confidence="low"))
    out, st = await _run(agent_ctx, a, ws, p, None)
    assert st.tool_logs[0].error_code == "research_unavailable"
    assert out.research_available is False and "couldn't do live research" in out.render()


async def test_gives_up_after_one_repair(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    bad = brief([{"claim": "c", "source_url": "https://nowhere.example", "source_title": "t"}])
    p = ScriptedProvider().on("shared.researcher", bad, bad)
    with pytest.raises(AgentError):
        await _run(agent_ctx, a, ws, p, None)
