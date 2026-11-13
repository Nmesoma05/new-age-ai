"""Agent 17: business.ads_planner."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.business import ADS_PLANNER
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final
from tests.business.helpers import biz_ws

REQ = "Plan December ads\nDate range: 2026-12-01 to 2026-12-24"


def ads(creatives=None, start="2026-12-01"):
    return final({"objective": "December party bookings", "readiness_note": "Small test is sensible: there is a budget.",
                  "start_date": start, "end_date": "2026-12-24",
                  "platforms": [{"channel": "meta_ads", "why": "Hosts are on Instagram", "audience_targeting": "Awka, 25-45",
                                 "formats": ["carousel"], "budget_note": "Part of the NGN 50,000 monthly budget"}],
                  "creatives": creatives or [{"channel": "meta_ads", "headline": "Party food, on time",
                                              "primary_text": "Home-style trays delivered same day.", "call_to_action": "Order now"}],
                  "test_plan": "Two headlines for a week", "measurement": ["WhatsApp enquiries from ads"],
                  "compliance_notes": ["Check the platform's food ad policy"], "uncertainties": [], "warnings": [],
                  "memory_candidates": []})


async def _run(agent_ctx, a, ws, p):
    async with agent_ctx(a, ws, provider=p) as ctx:
        return await run_agent(ADS_PLANNER, ctx, RunState(REQ), [LLMMessage("user", "## User request\n" + REQ)])


async def test_ad_plan(client, signup, make_workspace, agent_ctx):
    a, ws = await biz_ws(client, signup, make_workspace)
    out = await _run(agent_ctx, a, ws, ScriptedProvider().on("business.ads_planner", call("get_profile", {}), ads()))
    assert "**Check before launching:**" in out.render()


async def test_dates_stray_platforms_and_fake_offers(client, signup, make_workspace, agent_ctx):
    a, ws = await biz_ws(client, signup, make_workspace)
    bad = ads(start="2026-11-20", creatives=[{"channel": "google_search_ads", "headline": "50% off all trays",
                                             "primary_text": "From ₦9,999", "call_to_action": "Order"}])
    p = ScriptedProvider().on("business.ads_planner", call("get_profile", {}), bad, bad)
    with pytest.raises(AgentError):
        await _run(agent_ctx, a, ws, p)
    msg = p.sent_to("business.ads_planner")[2].messages[-1].content
    assert "exactly 2026-12-01" in msg and "google_search_ads" in msg and "50%" in msg
