"""Agent 27: freelancer.pricing_advisor. Every price is labelled by its basis; user's currency only."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.freelancer import PRICING_ADVISOR
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final
from tests.freelancer.helpers import fl_ws

MSG = "Package and price my services\nRate floor: USD 5.77 per hour (from your income goal of USD 600 a month)"


def pkg(**kw):
    p = {"name": "Onboarding audit", "for_who": "Early-stage fintechs", "deliverables": ["Annotated review", "Fix list"],
         "timeline": "5 days", "pricing_model": "fixed", "price_low": 150, "price_high": 250, "currency": "USD",
         "basis": "suggested_starting_point", "rationale": "Small, low-risk first offer"}
    p.update(kw)
    return p


def guide(packages):
    return final({"packages": packages, "pricing_notes": ["Raise prices after 3 projects"],
                  "scope_protection": ["50% deposit", "2 revision rounds"],
                  "cross_border": ["Confirm how the client can pay you and the fees on each side"], "upsells": [],
                  "missing_information": [], "uncertainties": [], "warnings": [], "memory_candidates": []})


async def _run(agent_ctx, a, ws, p, msg=MSG):
    async with agent_ctx(a, ws, provider=p) as ctx:
        return await run_agent(PRICING_ADVISOR, ctx, RunState(msg), [LLMMessage("user", msg)])


async def test_labelled_packages(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    out = await _run(agent_ctx, a, ws, ScriptedProvider().on("freelancer.pricing_advisor", call("get_profile", {}), guide(
        [pkg(), pkg(name="Hourly support", pricing_model="hourly", price_low=8, price_high=12, basis="your_income_goal")])))
    md = out.render()
    assert "suggested starting point: test it with real clients" in md and "meets your income goal" in md


async def test_bad_basis_and_currency(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    bad = guide([pkg(basis="your_rates"), pkg(name="EU", currency="EUR"), pkg(name="Odd", price_low=300, price_high=100)])
    p = ScriptedProvider().on("freelancer.pricing_advisor", call("get_profile", {}), bad, bad)
    with pytest.raises(AgentError):
        await _run(agent_ctx, a, ws, p)
    msg = p.sent_to("freelancer.pricing_advisor")[2].messages[-1].content
    assert "basis 'your_rates' needs a price" in msg and "not EUR" in msg and "price_high is below" in msg


async def test_income_goal_basis_needs_floor(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    bad = guide([pkg(basis="your_income_goal")])
    p = ScriptedProvider().on("freelancer.pricing_advisor", call("get_profile", {}), bad, bad)
    with pytest.raises(AgentError):
        await _run(agent_ctx, a, ws, p, msg="Package my services")
    assert "no rate floor was computed" in p.sent_to("freelancer.pricing_advisor")[2].messages[-1].content
