"""Stage 5: the whole engine through the real HTTP API, database and RLS. Only the LLM is scripted."""
import pytest

from tests.ai.helpers import conversation, reply, route, send
from tests.ai.scripted import call, final
from tests.ai.test_tools import FakeResearch


@pytest.fixture
def research():
    return FakeResearch()


async def test_multi_agent_pipeline_doc_research_strategy_and_save(client, signup, make_workspace, upload, provider,
                                                                  owner_db):
    a = await signup("Ada", product="business")
    ws = await make_workspace(a, "Mama Nkechi's Kitchen", product="business")
    doc = await upload(a, ws, "menu.txt", b"Menu: small chops tray, jollof party pack. We deliver in Awka.")
    conv = await conversation(client, a, ws)
    from tests.ai.agents.test_04_aida_strategist import plan
    provider.on("router", route("business.aida_strategist", document_ids=[doc["id"]], needs_research=True,
                                user_requested_save=True, task_summary="AIDA plan for party trays"))
    provider.on("shared.document_analyst",
                call("read_document", {"document_id": doc["id"], "start_chunk": 0, "max_chunks": 4}),
                final({"summary": "Party food menu; delivery in Awka.", "key_points": [
                    {"point": "Delivers in Awka", "ref": f"doc:{doc['id']}#0"}], "action_items": [],
                    "embedded_instructions": [], "uncertainties": [], "warnings": []}))
    provider.on("shared.researcher", call("web_search", {"query": "party catering trends", "max_results": 2}),
                final({"question": "trends", "research_available": True, "findings": [
                    {"claim": "Cold brew sales rose", "source_url": "https://news.example/coffee",
                     "source_title": "Coffee trends"}], "gaps": [], "confidence": "low", "uncertainties": [],
                    "warnings": []}))
    provider.on("business.aida_strategist", plan())
    r = await send(client, a, ws, conv, "Plan a month of posts to sell party trays, using my menu, and save it")
    assert r.status_code == 201, r.text
    run = r.json()["run"]
    assert run["agent"] == "business.aida_strategist" and run["status"] == "succeeded"
    assert run["output"]["stages"][0]["stage"] == "attention" and run["saved_asset_id"]
    # the strategist received both briefs as fenced data, after the support agents ran
    task = provider.sent_to("business.aida_strategist")[0].messages[-1].content
    assert "agent:shared.document_analyst" in task and "agent:shared.researcher" in task
    assert task.index("<untrusted_data") < task.index("Delivers in Awka")
    detail = (await client.get(f"/v1/workspaces/{ws}/runs/{run['id']}", headers=a.h)).json()
    assert [(t["agent"], t["tool"]) for t in detail["tool_calls"]] == [
        ("shared.document_analyst", "read_document"), ("shared.researcher", "web_search")]
    assert detail["llm_calls"] == 6 and detail["tainted"] is True
    assert set(detail["route"]["spec_versions"]) == {"router", "shared.document_analyst", "shared.researcher",
                                                     "business.aida_strategist"}
    usage = owner_db.execute("SELECT agent, counted_free FROM ai_usage_records ORDER BY created_at").fetchall()
    assert [u[0] for u in usage] == ["router", "shared.document_analyst", "shared.document_analyst",
                                     "shared.researcher", "shared.researcher", "business.aida_strategist"]
    assert [u[1] for u in usage].count(True) == 1  # one request = one Free generation
    asset = owner_db.execute("SELECT type FROM assets WHERE id = %s", (run["saved_asset_id"],)).fetchone()
    assert asset == ("content_plan",)
    assert "### Attention" in r.json()["assistant_message"]["content"]


async def test_clarify_unsupported_and_wrong_product_are_free(client, signup, make_workspace, provider, owner_db):
    a = await signup("Ada", product="business")
    ws = await make_workspace(a, "Shop", product="business")
    conv = await conversation(client, a, ws)
    provider.on("router", route("clarify", clarifying_question="Which product do you want to promote?"))
    r = (await send(client, a, ws, conv, "make me something")).json()
    assert r["run"]["status"] == "clarify" and r["assistant_message"]["content"] == "Which product do you want to promote?"
    provider.on("router", route("unsupported", unsupported_reason="I can't generate video files."))
    r = (await send(client, a, ws, conv, "render a 30s video ad")).json()
    assert r["run"]["status"] == "unsupported" and "can't generate video files" in r["assistant_message"]["content"]
    provider.on("router", route("business.assistant", belongs_to="freelancer"))
    r = (await send(client, a, ws, conv, "write my CV")).json()
    assert r["run"]["status"] == "unsupported" and "Freelancer Growth" in r["assistant_message"]["content"]
    assert owner_db.execute("SELECT count(*) FROM ai_usage_records WHERE counted_free").fetchone()[0] == 0
    assert (await client.get(f"/v1/orgs/{a.org_id}/usage", headers=a.h)).json()["free_used_this_month"] == 0


async def test_explicit_agent_choice_skips_router_and_is_scoped(client, signup, make_workspace, provider):
    a = await signup("Ada")
    ws = await make_workspace(a)
    conv = await conversation(client, a, ws)
    r = await send(client, a, ws, conv, "plan", agent="business.aida_strategist")
    assert r.status_code == 422 and r.json()["code"] == "agent_not_available"
    from tests.ai.agents.test_03_content_writer import draft, pack
    provider.on("creator.content_writer", pack(draft()))
    r = await send(client, a, ws, conv, "one post", agent="creator.content_writer")
    assert r.status_code == 201 and not provider.sent_to("router")


async def test_router_failure_falls_back_to_assistant(client, signup, make_workspace, provider):
    a = await signup("Ada")
    ws = await make_workspace(a)
    conv = await conversation(client, a, ws)
    bad = route("business.aida_strategist")  # not offered in a creator workspace, twice
    provider.on("router", bad, bad)
    r = (await send(client, a, ws, conv, "hello")).json()
    assert r["run"]["agent"] == "creator.assistant"
    assert "Routing was unclear" in " ".join(r["run"]["warnings"])


async def test_invalid_output_fails_cleanly_and_rolls_back_side_effects(client, signup, make_workspace, provider,
                                                                        owner_db):
    a = await signup("Ada")
    ws = await make_workspace(a)
    conv = await conversation(client, a, ws)
    provider.on("router", route("creator.assistant"))
    provider.on("creator.assistant",
                call("propose_external_action", {"kind": "publish_post", "title": "Promo", "content": "x",
                                                 "platform": "x", "recipient": None, "amount": None, "currency": None}),
                reply("I've posted it."), reply("I've published it now."))
    r = await send(client, a, ws, conv, "post the promo")
    assert r.status_code == 422 and r.json()["code"] == "ai_output_invalid"
    assert owner_db.execute("SELECT count(*) FROM pending_actions").fetchone()[0] == 0
    assert owner_db.execute("SELECT count(*) FROM messages").fetchone()[0] == 0
    run = owner_db.execute("SELECT status, error_code, agent FROM agent_runs").fetchall()
    assert run == [("failed", "output_invalid", "creator.assistant")]
    assert owner_db.execute("SELECT count(*) FROM ai_usage_records WHERE counted_free").fetchone()[0] == 0
    assert owner_db.execute("SELECT count(*) FROM tool_calls").fetchone()[0] == 1
    actions = [x[0] for x in owner_db.execute("SELECT action FROM audit_events").fetchall()]
    assert "ai.run_failed" in actions


async def test_memory_from_user_words_then_used_next_turn(client, signup, make_workspace, provider):
    a = await signup("Ada")
    ws = await make_workspace(a, "Client A")
    conv = await conversation(client, a, ws)
    msg = "Remember that we never use the word cheap in captions."
    provider.on("router", route("creator.assistant", explicit_memory_request=True))
    provider.on("creator.assistant", reply("Noted.", memory_candidates=[
        {"kind": "brand_rule", "content": "Never use the word 'cheap' in captions",
         "user_quote": "we never use the word cheap in captions", "visibility": "workspace"}]))
    r = (await send(client, a, ws, conv, msg)).json()
    assert r["run"]["memory_saved"][0]["status"] == "active"
    provider.on("router", route("creator.assistant"))
    provider.on("creator.assistant", reply("Here's a caption."))
    await send(client, a, ws, conv, "write a caption about our sale")
    task = provider.sent_to("creator.assistant")[-1].messages[-1].content
    assert "Workspace memory (set by the user)" in task and "cheap" in task
    listed = (await client.get(f"/v1/workspaces/{ws}/memory", headers=a.h)).json()["data"]
    assert len(listed) == 1 and listed[0]["source"] == "user_stated"


async def test_conversation_summary_rolls_forward(client, signup, make_workspace, provider, owner_db):
    a = await signup("Ada")
    ws = await make_workspace(a)
    conv = await conversation(client, a, ws)
    org = str(a.org_id)
    for i in range(13):
        for role in ("user", "assistant"):
            owner_db.execute("INSERT INTO messages (conversation_id, workspace_id, org_id, role, content) "
                             "VALUES (%s, %s, %s, %s, %s)", (conv, ws, org, role, f"old-{role}-{i}"))
    provider.on("shared.summarizer", final({"summary": "We agreed on a coffee-week campaign.", "open_items": []}))
    r = await send(client, a, ws, conv, "next")
    assert r.status_code == 201
    summary, through = owner_db.execute("SELECT summary, summary_through FROM conversations").fetchone()
    assert summary == "We agreed on a coffee-week campaign." and through is not None
    await send(client, a, ws, conv, "and then?")
    req = provider.sent_to("creator.assistant")[-1]
    text = " ".join(m.content for m in req.messages)
    assert "coffee-week campaign" in text and "old-user-0" not in text
    assert owner_db.execute("SELECT counted_free FROM ai_usage_records WHERE agent='shared.summarizer'").fetchone() == (False,)


async def test_runs_are_workspace_scoped(client, signup, make_workspace, provider):
    a, b = await signup("Ada"), await signup("Bola")
    ws, ws_b = await make_workspace(a), await make_workspace(b)
    conv = await conversation(client, a, ws)
    run_id = (await send(client, a, ws, conv, "hi")).json()["run"]["id"]
    assert (await client.get(f"/v1/workspaces/{ws}/runs/{run_id}", headers=a.h)).status_code == 200
    assert (await client.get(f"/v1/workspaces/{ws_b}/runs/{run_id}", headers=b.h)).status_code == 404
    assert len((await client.get(f"/v1/workspaces/{ws}/runs", headers=a.h)).json()["data"]) == 1


async def test_viewers_cannot_run_the_assistant(client, signup, activate_plan, provider):
    owner, viewer = await signup("Owner"), await signup("Viewer")
    org = (await client.post("/v1/orgs", headers=owner.h, json={"name": "Agency"})).json()["id"]
    await activate_plan(org, "team")
    await client.post(f"/v1/orgs/{org}/products", headers=owner.h, json={"product": "creator"})
    await client.post(f"/v1/orgs/{org}/members", headers=owner.h, json={"email": viewer.email, "role": "member"})
    ws = (await client.post(f"/v1/orgs/{org}/workspaces", headers=owner.h, json={"name": "C", "product": "creator"})).json()["id"]
    await client.post(f"/v1/workspaces/{ws}/members", headers=owner.h, json={"user_id": str(viewer.user_id), "role": "viewer"})
    conv = await conversation(client, owner, ws)
    r = await send(client, viewer, ws, conv, "hi")
    assert r.status_code == 403 and provider.requests == []
