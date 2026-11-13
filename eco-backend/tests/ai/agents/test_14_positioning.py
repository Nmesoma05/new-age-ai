"""Agent 14: business.positioning_strategist."""
from app.ai.agents.base import run_agent
from app.ai.agents.business import POSITIONING_STRATEGIST
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final
from tests.business.helpers import biz_ws


def guide(**kw):
    base = {"positioning_statement": "Same-day home-style party food in Awka.", "value_proposition": "Stress-free parties.",
            "elevator_pitch": "We cook like home and deliver on time, so your party just works.",
            "brand_personality": ["warm", "dependable"], "tone_guidance": "Friendly and reassuring.",
            "key_messages": [{"audience": "Party hosts", "message": "On time, every time.", "proof_points": ["Same-day delivery"]}],
            "taglines": ["Party food, done right.", "Home taste, on time."], "words_to_use": ["fresh"],
            "words_to_avoid": ["cheap"], "visual_direction": "Warm oranges, real food photos.", "do_and_dont": [],
            "uncertainties": [], "warnings": [], "memory_candidates": []}
    base.update(kw)
    return final(base)


async def test_positioning_and_no_invented_proof(client, signup, make_workspace, agent_ctx):
    a, ws = await biz_ws(client, signup, make_workspace)
    bad = guide(key_messages=[{"audience": "Hosts", "message": "Trusted by 500 families", "proof_points": ["Rated 4.9"]}])
    p = ScriptedProvider().on("business.positioning_strategist", call("get_profile", {}), bad, guide())
    async with agent_ctx(a, ws, provider=p) as ctx:
        out = await run_agent(POSITIONING_STRATEGIST, ctx, RunState("Position us"), [LLMMessage("user", "Position us")])
    assert out.taglines[0] == "Party food, done right." and "### Tagline options" in out.render()
    fix = p.sent_to("business.positioning_strategist")[2].messages[-1].content
    assert "500" in fix
