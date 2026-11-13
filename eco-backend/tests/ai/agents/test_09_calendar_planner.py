"""Agent 9: creator.calendar_planner."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.creator import CALENDAR_PLANNER
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, final

REQ = "Plan our content calendar.\nDate range: 2026-12-01 to 2026-12-14\nPlatforms: instagram, x"


def entry(d="2026-12-02", platform="instagram", time="18:30"):
    return {"date": d, "time": time, "platform": platform, "format": "carousel", "pillar": "Craft",
            "title": "How we roast", "idea": "Behind the scenes at the roaster"}


def plan(items, start="2026-12-01", end="2026-12-14"):
    return final({"strategy_summary": "Two pillars, steady rhythm.", "start_date": start, "end_date": end,
                  "posting_rhythm": "Instagram 3 times a week, X daily", "items": items, "uncertainties": [],
                  "warnings": [], "memory_candidates": []})


async def _run(agent_ctx, a, ws, p, msg=REQ):
    async with agent_ctx(a, ws, provider=p) as ctx:
        st = RunState(msg)
        return await run_agent(CALENDAR_PLANNER, ctx, st, [LLMMessage("user", "## User request\n" + msg)])


async def test_valid_plan(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    p = ScriptedProvider().on("creator.calendar_planner", plan([entry(), entry("2026-12-03", "x", "08:00")]))
    out = await _run(agent_ctx, a, ws, p)
    assert len(out.items) == 2 and "| 2026-12-03 08:00 | x |" in out.render()


async def test_period_platforms_dates_and_times_enforced(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    bad = plan([entry("2026-12-20"), entry(platform="tiktok"), entry(time="6pm"), entry("2026-02-30")],
               end="2026-12-31")
    p = ScriptedProvider().on("creator.calendar_planner", bad, bad)
    with pytest.raises(AgentError) as e:
        await _run(agent_ctx, a, ws, p)
    msg = p.sent_to("creator.calendar_planner")[1].messages[-1].content
    for expected in ("exactly 2026-12-01 to 2026-12-14", "2026-12-20", "tiktok", "HH:MM", "2026-02-30"):
        assert expected in msg, expected
    assert e.value.code == "output_invalid"
