from tests.ai.scripted import final


def route(agent, **kw):
    base = {"agent": agent, "task_summary": kw.pop("task_summary", "Do the task"), "belongs_to": "this_workspace",
            "document_ids": [], "needs_research": False, "user_requested_save": False,
            "explicit_memory_request": False, "confidence": 0.9, "clarifying_question": None,
            "unsupported_reason": None}
    base.update(kw)
    return final(base, tokens=(200, 30))


def reply(text, **kw):
    return final({"reply": text, "follow_ups": [], "uncertainties": kw.pop("uncertainties", []),
                  "warnings": kw.pop("warnings", []), "memory_candidates": kw.pop("memory_candidates", [])})


async def conversation(client, acct, ws):
    return (await client.post(f"/v1/workspaces/{ws}/conversations", headers=acct.h, json={})).json()["id"]


async def send(client, acct, ws, conv, content, **kw):
    return await client.post(f"/v1/workspaces/{ws}/conversations/{conv}/messages", headers=acct.h,
                             json={"content": content, **kw})
