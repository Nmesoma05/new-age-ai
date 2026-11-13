"""Agent 21: freelancer.cv_writer. Built only from the profile; job posts shape emphasis, never content."""
import pytest

from app.ai.agents.base import AgentError, run_agent
from app.ai.agents.freelancer import CV_WRITER
from app.ai.providers.base import LLMMessage
from app.ai.runstate import RunState
from tests.ai.scripted import ScriptedProvider, call, final
from tests.freelancer.helpers import fl_ws

JOB = "Senior Product Designer. 5+ years in fintech. Must know Figma, design systems and SQL. Remote (EMEA)."
MSG = "Tailor my CV for this role\nTarget role: Product designer\nTarget market: europe"


def cv(experience=None, market="europe", matched=("Figma", "fintech"), missing=("design systems", "SQL"), summary=None, extra=None):
    body = {"target_role": "Product designer", "market": market, "headline": "UI/UX designer · Figma · fintech onboarding",
            "summary": summary or "UI/UX designer with internship experience redesigning savings-app onboarding.",
            "experience": experience if experience is not None else [
                {"title": "UI Designer (intern)", "organisation": "Kola Studio", "period": "Jan 2025 - Jun 2025",
                 "source_ref": "profile:experiences[0]",
                 "bullets": [{"text": "Redesigned the onboarding screens for a savings app", "source_ref": "profile:experiences[0]"}]}],
            "projects": [{"name": "Savings app onboarding redesign", "detail": "Cut onboarding from 7 screens to 4",
                          "source_ref": "profile:portfolio[0]"}],
            "skills": [{"name": "Figma", "source_ref": "profile:skills[0]"}],
            "education": [{"name": "B.Eng. Computer Engineering", "detail": "UNIZIK, 2019-2024", "source_ref": "profile:education[0]"}],
            "certifications": [{"name": "Google UX Design Certificate", "detail": "Google, 2024", "source_ref": "profile:certifications[0]"}],
            "keywords_matched": list(matched), "keywords_missing": list(missing), "tailoring_notes": ["Led with onboarding work"],
            "suggestions": ["Suggestion: add a design-system practice project"], "missing_information": [],
            "uncertainties": [], "warnings": [], "memory_candidates": []}
    body.update(extra or {})
    return final(body)


async def _run(agent_ctx, a, ws, p):
    async with agent_ctx(a, ws, provider=p) as ctx:
        st = RunState(MSG)
        st.corpus.append(JOB)  # the job post reaches the model as external data, not as the user's words
        task = f"<untrusted_data>{JOB}</untrusted_data>\n## User request\n{MSG}"
        return await run_agent(CV_WRITER, ctx, st, [LLMMessage("user", task)])


async def test_tailored_cv_from_profile(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    out = await _run(agent_ctx, a, ws, ScriptedProvider().on("freelancer.cv_writer", call("get_profile", {}), cv()))
    md = out.render()
    assert "**UI Designer (intern)**, Kola Studio" in md and "add only if true" in md and "Continental Europe" in md


async def test_job_post_cannot_become_experience(client, signup, make_workspace, agent_ctx):
    a, ws = await fl_ws(client, signup, make_workspace)
    bad = cv(experience=[{"title": "Senior Product Designer", "organisation": "Kola Studio", "period": "2020 - 2025",
                          "source_ref": "profile:experiences[0]",
                          "bullets": [{"text": "Built design systems in SQL-heavy fintech teams", "source_ref": "user_message"}]}],
             market="us", matched=("Figma", "SQL"), summary="Product designer with 5+ years in fintech.",
             extra={"certifications": [{"name": "Certified Scrum Master", "detail": "", "source_ref": "profile:certifications[0]"}]})
    p = ScriptedProvider().on("freelancer.cv_writer", call("get_profile", {}), bad, bad)
    with pytest.raises(AgentError):
        await _run(agent_ctx, a, ws, p)
    msg = p.sent_to("freelancer.cv_writer")[2].messages[-1].content
    for expect in ("don't rename or invent roles", "Bullets without a profile ref", "Certified Scrum Master",
                   "move these to keywords_missing: SQL", "set market to europe", "5+ years"):
        assert expect in msg, expect
