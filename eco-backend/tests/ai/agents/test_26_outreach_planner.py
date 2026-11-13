"""Agent 26: freelancer.outreach_planner. Only prospects the user named; drafts, never 'sent'."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.freelancer import OUTREACH_PLANNER
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final
from tests.freelancer.helpers import fl_ws

MSG = "Help me find fintech clients. I'm thinking of approaching Kudi Savings."


def plan(prospects=None, text="Hi [NAME], I noticed your sign-up flow has [DETAIL]. I redesign onboarding for savings apps."):
    return final({"offer_summary": "Onboarding UX audit for savings and payments apps",
                  "ideal_clients": [{"segment": "Early-stage African fintechs", "why_fit": "Matches your case study",
                                     "where_to_find": ["LinkedIn", "startup newsletters"], "buying_signals": ["New app launch"]}],
                  "prospects": prospects if prospects is not None else [{"name": "Kudi Savings", "angle": "Their sign-up", "research_to_do": ["Try their app"]}],
                  "research_checklist": ["Use their product first"],
                  "messages": [{"channel": "linkedin", "purpose": "first_touch", "subject": None, "text": text}],
                  "weekly_routine": ["10 personalised messages"], "metrics": ["Replies"],
                  "claims": [{"claim": "redesign onboarding for savings apps", "source_ref": "profile:portfolio[0]"}],
                  "missing_information": [], "uncertainties": [], "warnings": [], "memory_candidates": []})


async def _run(agent_ctx, a, ws, p):
    async with agent_ctx(a, ws, provider=p) as ctx:
        return await run_agent(OUTREACH_PLANNER, ctx, RunState(MSG), [LLMMessage("user", MSG)])


async def test_plan(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    out = await _run(agent_ctx, a, ws, ScriptedProvider().on("freelancer.outreach_planner", call("get_profile", {}), plan()))
    assert "Message drafts (not sent)" in out.render()


async def test_invented_prospects_and_sent_claims(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    bad = plan(prospects=[{"name": "Flutterwave", "angle": "x", "research_to_do": []}],
               text="I've sent this to 20 founders already.")
    p = ScriptedProvider().on("freelancer.outreach_planner", call("get_profile", {}), bad, bad)
    with pytest.raises(AgentError):
        await _run(agent_ctx, a, ws, p)
    msg = p.sent_to("freelancer.outreach_planner")[2].messages[-1].content
    assert "remove: Flutterwave" in msg and "posted/sent/paid" in msg
