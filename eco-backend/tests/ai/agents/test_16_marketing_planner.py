"""Agent 16: business.marketing_planner."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.business import MARKETING_PLANNER
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final
from tests.business.helpers import biz_ws


def plan(months=3, timeline=None, budget="NGN 50,000 a month: most on WhatsApp status boosts and reviews", target="20"):
    return final({"executive_summary": "Win more weekend parties through WhatsApp and local search.", "plan_months": months,
                  "objectives": [{"objective": "More weekend orders", "metric": "orders per weekend", "target": target}],
                  "target_segments": ["Party hosts"],
                  "channel_plan": [{"channel": "whatsapp", "role": "Orders and follow-up", "tactics": ["Status updates"],
                                    "effort": "low", "budget_share": "No paid budget"}],
                  "timeline": timeline or [{"period": f"Month {i}", "focus": "x", "actions": ["y"]} for i in range(1, months + 1)],
                  "budget": budget, "kpis": [{"metric": "orders", "how_to_measure": "Order log"}], "risks": [],
                  "uncertainties": [], "warnings": [], "memory_candidates": []})


async def _run(agent_ctx, a, ws, p, msg="Make a plan\nPlan length: 3 months"):
    async with agent_ctx(a, ws, provider=p) as ctx:
        return await run_agent(MARKETING_PLANNER, ctx, RunState(msg), [LLMMessage("user", "## User request\n" + msg)])


async def test_plan_uses_owner_budget_and_target(client, signup, make_workspace, agent_ctx):
    a, ws = await biz_ws(client, signup, make_workspace)
    p = ScriptedProvider().on("business.marketing_planner", call("get_profile", {}), plan())
    out = await _run(agent_ctx, a, ws, p)
    assert out.plan_months == 3 and "| whatsapp | Orders and follow-up | low | No paid budget |" in out.render()


async def test_length_timeline_and_invented_budget_enforced(client, signup, make_workspace, agent_ctx):
    a, ws = await biz_ws(client, signup, make_workspace)
    bad = plan(months=6, timeline=[{"period": "Month 1", "focus": "x", "actions": ["y"]}],
               budget="Spend ₦400,000 on Meta ads", target="150")
    p = ScriptedProvider().on("business.marketing_planner", call("get_profile", {}), bad, bad)
    with pytest.raises(AgentError):
        await _run(agent_ctx, a, ws, p)
    msg = p.sent_to("business.marketing_planner")[2].messages[-1].content
    assert "exactly 3 months" in msg and "one timeline entry per month" in msg and "₦400,000" in msg
