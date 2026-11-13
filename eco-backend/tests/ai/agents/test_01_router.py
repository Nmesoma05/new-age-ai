"""Agent 1: router. Built and tested before any other agent."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.specs import AGENT_MENU, ROUTER, RouteDecision, offered_agents
from app.ai.providers.base import LLMMessage
from app.ai.providers.schema import schema_stats, strict_schema
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, final

BASE = {"agent": "creator.content_writer", "task_summary": "Write 3 posts", "belongs_to": "this_workspace",
        "document_ids": [], "needs_research": False, "user_requested_save": True, "explicit_memory_request": False,
        "confidence": 0.86, "clarifying_question": None, "unsupported_reason": None}


def test_schema_and_menu():
    assert schema_stats(strict_schema(RouteDecision))["unions"] == 2
    assert offered_agents("business") == [
        "business.assistant", "business.aida_strategist", "business.profile_builder", "business.positioning_strategist",
        "business.market_analyst", "business.marketing_planner", "business.ads_planner", "business.growth_strategist",
        "business.performance_analyst", "shared.document_analyst", "shared.researcher"]
    assert not any(a.startswith("creator.") for a in offered_agents("business"))
    assert all(a in RouteDecision.model_fields["agent"].annotation.__args__ for a in AGENT_MENU)


async def _route(agent_ctx, acct, ws, provider, docs=()):
    async with agent_ctx(acct, ws, provider=provider) as ctx:
        st = RunState("Write three Instagram posts for the new menu and save them")
        st.doc_choices = set(docs)
        out = await run_agent(ROUTER, ctx, st, [LLMMessage("user", "## User request\n" + st.user_message)])
        return out, st


async def test_routes_and_is_fast_tier_without_tools(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    p = ScriptedProvider().on("router", final(BASE))
    out, st = await _route(agent_ctx, a, ws, p)
    assert out.agent == "creator.content_writer" and out.user_requested_save
    req = p.sent_to("router")[0]
    assert req.tier == "fast" and req.tools == [] and req.output_schema["additionalProperties"] is False
    assert "untrusted_data" in req.system  # security rules always present
    assert st.llm_calls[0].agent == "router" and st.llm_calls[0].model == "scripted"


async def test_wrong_product_agent_is_repaired(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)  # creator workspace
    p = ScriptedProvider().on("router", final({**BASE, "agent": "business.aida_strategist"}), final(BASE))
    out, _ = await _route(agent_ctx, a, ws, p)
    assert out.agent == "creator.content_writer"
    repair = p.sent_to("router")[1].messages[-1].content
    assert "isn't available in a creator workspace" in repair


async def test_invented_document_ids_rejected(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    bad = {**BASE, "agent": "shared.document_analyst", "document_ids": ["11111111-1111-1111-1111-111111111111"]}
    p = ScriptedProvider().on("router", final(bad), final(bad))
    with pytest.raises(AgentError) as e:
        await _route(agent_ctx, a, ws, p, docs=["22222222-2222-2222-2222-222222222222"])
    assert e.value.code == "output_invalid" and "listed documents" in e.value.message


async def test_clarify_and_unsupported_need_text(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    p = ScriptedProvider().on("router", final({**BASE, "agent": "clarify"}),
                              final({**BASE, "agent": "clarify", "clarifying_question": "Which client is this for?"}))
    out, _ = await _route(agent_ctx, a, ws, p)
    assert out.clarifying_question == "Which client is this for?"


async def test_malformed_json_then_refusal(client, signup, make_workspace, agent_ctx):
    from app.ai.providers.base import LLMResponse
    a = await signup("Ada")
    ws = await make_workspace(a)
    junk = LLMResponse(text="{not json", tool_calls=[], stop="end", model="m", tokens_in=1, tokens_out=1, latency_ms=1)
    p = ScriptedProvider().on("router", junk, final(BASE))
    out, st = await _route(agent_ctx, a, ws, p)
    assert out.agent == "creator.content_writer" and len(st.llm_calls) == 2
    refusal = LLMResponse(text="no", tool_calls=[], stop="refusal", model="m", tokens_in=1, tokens_out=1, latency_ms=1)
    with pytest.raises(AgentError) as e:
        await _route(agent_ctx, a, ws, ScriptedProvider().on("router", refusal))
    assert e.value.code == "model_refused"
