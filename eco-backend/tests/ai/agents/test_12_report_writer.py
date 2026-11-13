"""Agent 12: creator.report_writer. Every number must come from the recorded data in the task."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.creator import REPORT_WRITER
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, final

DATA = ("Performance summary (calculated from data the team entered manually):\nPosts: 4\nImpressions: 12,400\n"
        "Engagements: 930\nEngagement rate: 7.5%\nTop post: 'Roast day' with 5,100 impressions")


def narrative(headline="Roast day led with 5,100 impressions", caveats=("Entered manually by the team.",)):
    return final({"headline": headline, "highlights": [{"point": "Engagement rate was 7.5% across 4 posts",
                                                         "metric_basis": "Engagement rate"}],
                  "what_to_improve": ["Post more behind-the-scenes"], "next_actions": ["Repeat roast day monthly"],
                  "data_caveats": list(caveats), "uncertainties": [], "warnings": []})


async def _run(agent_ctx, a, ws, p):
    async with agent_ctx(a, ws, provider=p) as ctx:
        st = RunState("Write the monthly report")
        return await run_agent(REPORT_WRITER, ctx, st, [LLMMessage("user", DATA + "\n\n## User request\nWrite the monthly report")])


async def test_uses_only_recorded_figures(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    out = await _run(agent_ctx, a, ws, ScriptedProvider().on("creator.report_writer", narrative()))
    assert "About this data" in out.render()


async def test_invented_figures_and_missing_caveats_rejected(client, signup, make_workspace, agent_ctx):
    a = await signup("Ada")
    ws = await make_workspace(a)
    bad = narrative(headline="Reach grew 38% to 20,000 people")
    p = ScriptedProvider().on("creator.report_writer", final({**__import__("json").loads(narrative().text),
                                                              "data_caveats": []}), bad, bad)
    with pytest.raises(AgentError) as e:
        await _run(agent_ctx, a, ws, p)
    assert "38" in e.value.message and "20,000" in e.value.message
