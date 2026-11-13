"""Agent 4: business.aida_strategist (Division 2's AIDA social content strategy)."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.specs import AIDA_STRATEGIST, AidaPlan
from app.ai.providers.base import LLMMessage
from app.ai.providers.schema import schema_stats, strict_schema
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final


def post(platform="instagram", copy="Small chops for your next party, from [YOUR PRICE]."):
    return {"platform": platform, "format": "reel", "idea": "Tray reveal", "draft_copy": copy,
            "call_to_action": "Order on WhatsApp"}


def plan(stages=("attention", "interest", "desire", "action"), platforms=("instagram", "whatsapp"), copy=None):
    return final({
        "objective": "More party-tray orders", "audience": "Event planners and families in Awka",
        "platforms": list(platforms),
        "stages": [{"stage": s, "goal": f"{s} goal", "key_message": "Fresh, on time",
                    "posts": [post(copy=copy) if copy else post()]} for s in stages],
        "posting_rhythm": "Instagram 3 times a week; WhatsApp status daily",
        "kpis": [{"metric": "WhatsApp enquiries per week", "why": "Shows interest turning into orders"}],
        "budget_note": "No ad spend needed to start; boost the best reel later if it performs.",
        "uncertainties": [], "warnings": [], "memory_candidates": []})


def test_schema_within_vendor_limits():
    assert schema_stats(strict_schema(AidaPlan))["unions"] <= 16


async def test_full_aida_plan(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada", product="business")
    ws = await make_workspace(a, "Mama Nkechi's Kitchen", product="business")
    await client.put(f"/v1/workspaces/{ws}/business-profile", headers=a.h, json={
        "business_name": "Mama Nkechi's Kitchen", "industry": "food", "location": "Awka", "primary_goal": "sales",
        "offers": [{"name": "Small chops tray", "price": "NGN 25,000"}]})
    p = ScriptedProvider().on("business.aida_strategist", call("get_profile", {}),
                              plan(copy="Party tray from NGN 25,000. Order today."))
    async with agent_ctx(a, ws, provider=p) as ctx:
        out = await run_agent(AIDA_STRATEGIST, ctx, RunState("Plan a month of posts"),
                              [LLMMessage("user", "## User request\nPlan a month of posts")])
    assert [s.stage for s in out.stages] == ["attention", "interest", "desire", "action"]
    text = out.render()
    assert "### Attention" in text and "### Action" in text and "NGN 25,000" in text  # price came from the profile


async def test_stage_order_and_platform_consistency(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada", product="business")
    ws = await make_workspace(a, "Shop", product="business")
    wrong_order = plan(stages=("interest", "attention", "desire", "action"))
    stray_platform = plan(platforms=("whatsapp",))  # posts use instagram
    p = ScriptedProvider().on("business.aida_strategist", wrong_order, stray_platform)
    async with agent_ctx(a, ws, provider=p) as ctx:
        with pytest.raises(AgentError) as e:
            await run_agent(AIDA_STRATEGIST, ctx, RunState("plan"), [LLMMessage("user", "plan")])
        assert e.value.code == "output_invalid" and "instagram" in e.value.message
    msgs = p.sent_to("business.aida_strategist")[1].messages[-1].content
    assert "in that order" in msgs


async def test_invented_price_rejected(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada", product="business")
    ws = await make_workspace(a, "Shop", product="business")
    p = ScriptedProvider().on("business.aida_strategist", plan(copy="Trays from ₦18,000!"), plan())
    async with agent_ctx(a, ws, provider=p) as ctx:
        out = await run_agent(AIDA_STRATEGIST, ctx, RunState("plan"), [LLMMessage("user", "plan")])
    assert "[YOUR PRICE]" in out.stages[0].posts[0].draft_copy
