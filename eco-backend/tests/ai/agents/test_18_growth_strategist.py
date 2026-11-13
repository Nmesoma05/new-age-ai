"""Agent 18: business.growth_strategist (acquisition and retention)."""
from app.ai.agents.base import run_agent
from app.ai.agents.business import GROWTH_STRATEGIST
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, final
from tests.business.helpers import biz_ws


def growth(focus):
    return final({"focus": focus, "summary": "Turn happy hosts into repeat customers.",
                  "journey": [{"stage": "First order", "goal": "Delight"}, {"stage": "Repeat", "goal": "Next event"}],
                  "tactics": [{"name": "Thank-you follow-up", "channel": "whatsapp", "how_it_works": "Message after the event",
                               "steps": ["Send photo request"], "effort": "low", "cost_note": "Free", "metric": "repeat orders"},
                              {"name": "Referral thank-you", "channel": "referrals", "how_it_works": "[YOUR OFFER] for referrals",
                               "steps": ["Ask for one referral"], "effort": "low", "cost_note": "Cost of [YOUR OFFER]", "metric": "referrals"}],
                  "offers_or_hooks": ["[YOUR OFFER] on the next order"], "quick_wins": ["Message last month's customers"],
                  "measurement": ["Repeat orders per month"], "uncertainties": [], "warnings": [], "memory_candidates": []})


async def test_focus_must_match(client, signup, make_workspace, agent_ctx):
    a, ws = await biz_ws(client, signup, make_workspace)
    msg = "Help me keep customers\nFocus: retention"
    p = ScriptedProvider().on("business.growth_strategist", growth("acquisition"), growth("retention"))
    async with agent_ctx(a, ws, provider=p) as ctx:
        out = await run_agent(GROWTH_STRATEGIST, ctx, RunState(msg), [LLMMessage("user", msg)])
    assert out.focus == "retention" and "### Quick wins this week" in out.render()
    assert "set focus to retention" in p.sent_to("business.growth_strategist")[1].messages[-1].content
