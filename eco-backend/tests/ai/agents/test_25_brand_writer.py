"""Agent 25: freelancer.brand_writer. Platform limits, requested platforms, grounded claims."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.freelancer import BRAND_WRITER
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final
from tests.freelancer.helpers import fl_ws

MSG = "Write my bios and a couple of posts\nPlatforms: linkedin, x"


def kit(bios=None, posts=None, claims=None):
    return final({"positioning_line": "UI/UX designer making fintech onboarding simple",
                  "bios": bios or [{"platform": "x", "text": "UI/UX designer. Simple fintech onboarding. Figma."},
                                   {"platform": "linkedin", "text": "I design clear onboarding for fintech apps."}],
                  "posts": posts or [{"platform": "linkedin", "hook": "7 screens to 4",
                                      "text": "How I cut a savings app's onboarding from 7 screens to 4."}],
                  "content_ideas": ["Before/after breakdowns"],
                  "claims": claims or [{"claim": "Cut onboarding from 7 screens to 4", "source_ref": "profile:portfolio[0]"}],
                  "missing_information": [], "uncertainties": [], "warnings": [], "memory_candidates": []})


async def _run(agent_ctx, a, ws, p):
    async with agent_ctx(a, ws, provider=p) as ctx:
        return await run_agent(BRAND_WRITER, ctx, RunState(MSG), [LLMMessage("user", MSG)])


async def test_brand_kit(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    out = await _run(agent_ctx, a, ws, ScriptedProvider().on("freelancer.brand_writer", call("get_profile", {}), kit()))
    assert "### Post drafts" in out.render()


async def test_limits_platforms_claims(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    bad = kit(bios=[{"platform": "x", "text": "x" * 200}], posts=[{"platform": "tiktok", "hook": "h", "text": "t"}],
              claims=[{"claim": "Worked with Paystack", "source_ref": "profile:experiences[3]"}])
    p = ScriptedProvider().on("freelancer.brand_writer", call("get_profile", {}), bad, bad)
    with pytest.raises(AgentError):
        await _run(agent_ctx, a, ws, p)
    msg = p.sent_to("freelancer.brand_writer")[2].messages[-1].content
    assert "over 160" in msg and "remove tiktok" in msg and "Worked with Paystack" in msg
