"""Agent 2: the three product assistants (one spec template, per-product scope)."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.specs import (
    BUSINESS_ASSISTANT,
    CREATOR_ASSISTANT,
    FREELANCER_ASSISTANT,
)
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final


def reply(text, **kw):
    return final({"reply": text, "follow_ups": [], "uncertainties": [], "warnings": [], "memory_candidates": [], **kw})


async def _run(agent_ctx, acct, ws, spec, provider, msg="What tone should we use?"):
    async with agent_ctx(acct, ws, provider=provider) as ctx:
        st = RunState(msg)
        out = await run_agent(spec, ctx, st, [LLMMessage("user", "## User request\n" + msg)])
        return out, st


async def test_uses_profile_then_answers(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a, "Lagos Coffee Co.")
    await client.put(f"/v1/workspaces/{ws}/client-account", headers=a.h,
                     json={"client_name": "Lagos Coffee Co.", "brand_voice": {"tone": "warm, witty"}, "platforms": ["instagram"]})
    p = ScriptedProvider().on("creator.assistant", call("get_profile", {}), reply("Warm and witty, like the brand voice."))
    out, st = await _run(agent_ctx, a, ws, CREATOR_ASSISTANT, p)
    assert out.reply.startswith("Warm and witty")
    second = p.sent_to("creator.assistant")[1]
    assert second.messages[-1].role == "tool" and "warm, witty" in second.messages[-1].content
    assert {t.name for t in second.tools} == {"search_context", "get_profile", "list_documents", "read_document",
                                              "list_saved_outputs", "propose_external_action"}
    assert "Creator & Marketing Assistant" in second.system and '"Lagos Coffee Co."' in second.system


async def test_cannot_use_tools_outside_its_spec(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada", product="business")
    ws = await make_workspace(a, "Mama's Kitchen", product="business")
    p = ScriptedProvider().on("business.assistant", call("web_search", {"query": "x", "max_results": 2}),
                              reply("I can't research that here."))
    out, st = await _run(agent_ctx, a, ws, BUSINESS_ASSISTANT, p)
    assert st.tool_logs[0].status == "denied" and st.tool_logs[0].error_code == "tool_not_allowed"


async def test_claiming_to_have_posted_is_repaired(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    p = ScriptedProvider().on("creator.assistant", reply("Done! I've posted it to Instagram."),
                              reply("Here's the post, ready for you to publish."))
    out, st = await _run(agent_ctx, a, ws, CREATOR_ASSISTANT, p)
    assert "ready for you" in out.reply and len(st.llm_calls) == 2


async def test_invented_statistics_fail_twice_then_error(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada", product="freelancer")
    ws = await make_workspace(a, "Me", product="freelancer")
    bad = reply("Freelancers who niche down earn 47% more and charge $120 an hour.")
    p = ScriptedProvider().on("freelancer.assistant", bad, bad)
    with pytest.raises(AgentError) as e:
        await _run(agent_ctx, a, ws, FREELANCER_ASSISTANT, p, msg="Should I niche down?")
    assert e.value.code == "output_invalid" and "47%" in e.value.message


async def test_numbers_the_user_gave_are_fine(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada", product="freelancer")
    ws = await make_workspace(a, "Me", product="freelancer")
    p = ScriptedProvider().on("freelancer.assistant", reply("At ₦150,000 per logo you're mid-market; keep 20% for tax."))
    out, _ = await _run(agent_ctx, a, ws, FREELANCER_ASSISTANT, p,
                        msg="I charge NGN 150,000 per logo and set aside 20% for tax. Is that okay?")
    assert "150,000" in out.reply


async def test_publish_request_becomes_a_proposal(client, signup, make_workspace, agent_ctx, owner_db):
    a = await signup("Ada")
    ws = await make_workspace(a)
    p = ScriptedProvider().on("creator.assistant",
                              call("propose_external_action", {"kind": "publish_post", "title": "Friday promo",
                                                               "content": "Fresh beans Friday ☕", "platform": "instagram",
                                                               "recipient": None, "amount": None, "currency": None}),
                              reply("I've queued it for approval; it isn't live yet."))
    out, st = await _run(agent_ctx, a, ws, CREATOR_ASSISTANT, p, msg="Post the Friday promo on Instagram")
    assert len(st.proposals) == 1
    assert owner_db.execute("SELECT status FROM pending_actions").fetchone()[0] == "awaiting_approval"
