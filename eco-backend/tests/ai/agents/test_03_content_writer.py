"""Agent 3: creator.content_writer."""
from app.ai.agents.base import run_agent
from app.ai.agents.specs import CONTENT_WRITER, ContentPack
from app.ai.providers.base import LLMMessage
from app.ai.providers.schema import schema_stats, strict_schema
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final


def draft(platform="instagram", body="Monday mood: a warm cup and a fresh start.", **kw):
    return {"platform": platform, "format": "post", "hook": "Monday mood", "body": body, "thread_parts": [],
            "hashtags": ["LagosCoffee"], "call_to_action": "Order on WhatsApp", "visual_idea": "Steam over a cup", **kw}


def pack(*drafts):
    return final({"brief": "Weekly posts", "drafts": list(drafts), "uncertainties": [], "warnings": [],
                  "memory_candidates": []})


def test_schema_within_vendor_limits():
    stats = schema_stats(strict_schema(ContentPack))
    assert stats["unions"] <= 16


async def test_writes_with_brand_context_and_renders(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    await client.put(f"/v1/workspaces/{ws}/client-account", headers=a.h,
                     json={"client_name": "Lagos Coffee Co.", "brand_voice": {"tone": "warm"}, "platforms": ["instagram", "x"]})
    p = ScriptedProvider().on("creator.content_writer",
                              call("get_profile", {}, ("search_context", {"query": "brand rules", "sources": "memory"})),
                              pack(draft(), draft("x", body="Coffee first, emails second.", format="thread",
                                                  thread_parts=["Then the to-do list."])))
    async with agent_ctx(a, ws, provider=p) as ctx:
        st = RunState("Two posts for Monday")
        out = await run_agent(CONTENT_WRITER, ctx, st, [LLMMessage("user", "## User request\nTwo posts for Monday")])
    assert [l.tool for l in st.tool_logs] == ["get_profile", "search_context"]
    text = out.render()
    assert "### 2. x thread" in text and "2/ Then the to-do list." in text and "#LagosCoffee" in text


async def test_platform_length_enforced(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    long_x = draft("x", body="word " * 70)  # ~350 chars
    p = ScriptedProvider().on("creator.content_writer", pack(long_x), pack(draft("x", body="Short and sharp.")))
    async with agent_ctx(a, ws, provider=p) as ctx:
        out = await run_agent(CONTENT_WRITER, ctx, RunState("x post"), [LLMMessage("user", "x post")])
    assert out.drafts[0].body == "Short and sharp."
    assert "allows about 280" in p.sent_to("creator.content_writer")[1].messages[-1].content


async def test_invented_stats_and_prices_repaired(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    p = ScriptedProvider().on("creator.content_writer",
                              pack(draft(body="Rated #1 by 92% of Lagos! Only ₦2,500 a cup.")),
                              pack(draft(body="Lagos's favourite cup, for [YOUR PRICE].")))
    async with agent_ctx(a, ws, provider=p) as ctx:
        out = await run_agent(CONTENT_WRITER, ctx, RunState("promo"), [LLMMessage("user", "promo")])
    assert "[YOUR PRICE]" in out.drafts[0].body
    fix = p.sent_to("creator.content_writer")[1].messages[-1].content
    assert "92%" in fix and "₦2,500" in fix
