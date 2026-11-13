"""Agent 19: business.performance_analyst. Every number must come from recorded results."""

from app.ai.agents.base import run_agent
from app.ai.agents.business import PERFORMANCE_ANALYST
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, final
from tests.business.helpers import biz_ws

DATA = "Marketing results (recorded):\nSpend: NGN 30,000\nLeads: 60\nCustomers: 12\nCost per lead: NGN 500\n"


def analysis(headline="60 leads at NGN 500 each", shifts=()):
    return final({"headline": headline, "what_worked": [{"point": "WhatsApp brought 12 customers", "metric_basis": "Customers"}],
                  "what_to_improve": [], "budget_shifts": list(shifts), "next_actions": ["Keep following up leads"],
                  "data_caveats": ["Entered by the team"], "uncertainties": [], "warnings": []})


async def test_only_recorded_numbers(client, signup, make_workspace, agent_ctx):
    a, ws = await biz_ws(client, signup, make_workspace)
    bad = analysis(shifts=["Move 40% of spend to Google for a 3x return"])
    p = ScriptedProvider().on("business.performance_analyst", bad, analysis())
    async with agent_ctx(a, ws, provider=p) as ctx:
        out = await run_agent(PERFORMANCE_ANALYST, ctx, RunState("Analyse"), [LLMMessage("user", DATA + "## User request\nAnalyse")])
    assert out.headline.startswith("60 leads")
    assert "40" in p.sent_to("business.performance_analyst")[1].messages[-1].content
