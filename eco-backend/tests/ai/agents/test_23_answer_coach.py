"""Agent 23: freelancer.answer_coach. Feedback on a typed answer; the rewrite adds no facts."""
from app.ai.agents.base import run_agent
from app.ai.agents.freelancer import ANSWER_COACH
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, final
from tests.freelancer.helpers import fl_ws

MSG = ("Question: Tell me about a design you improved.\nMy answer: At Kola Studio I worked on a savings app's "
       "onboarding. People dropped off so I simplified it.")


def fb(improved):
    return final({"scores": {"structure": 3, "relevance": 4, "specificity": 2, "clarity": 4},
                  "overall": "Relevant, but light on detail.", "strengths": ["Real example"],
                  "improvements": ["Say what you changed and the result"], "improved_answer": improved,
                  "follow_up_question": "How did you test it?", "uncertainties": [], "warnings": []})


async def test_feedback_and_grounded_rewrite(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    bad = fb("At Kola Studio I cut drop-off by 35% and onboarding time by 50%.")
    good = fb("At Kola Studio I redesigned a savings app's onboarding, cutting it from 7 screens to 4 [ADD RESULT].")
    p = ScriptedProvider().on("freelancer.answer_coach", bad, good)
    async with agent_ctx(a, ws, provider=p) as ctx:
        st = RunState(MSG)
        st.profile_refs["profile:portfolio[0]"] = "Cut onboarding from 7 screens to 4"
        out = await run_agent(ANSWER_COACH, ctx, st, [LLMMessage("user", MSG)])
    assert "Specificity 2/5" in out.render() and "[ADD RESULT]" in out.improved_answer
    repair = p.sent_to("freelancer.answer_coach")[1].messages[-1].content
    assert "35" in repair and "50" in repair
