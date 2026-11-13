"""Stage 1: provider adapters. These check our translation to each vendor's documented wire format and back,
using httpx.MockTransport. They do not call the live APIs (no keys in CI); see docs/AI_ENGINE.md."""
import json

import httpx
import pytest
from pydantic import BaseModel, Field, SecretStr

from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.base import (
    LLMMessage,
    LLMRequest,
    ProviderError,
    ToolCall,
    ToolSpec,
)
from app.ai.providers.embeddings import HashEmbedder
from app.ai.providers.openai import OpenAIProvider
from app.ai.providers.schema import schema_stats, strict_schema
from app.core.config import get_settings


class Inner(BaseModel):
    label: str = Field(min_length=1, max_length=40)


class Out(BaseModel):
    title: str = Field(max_length=100)
    items: list[Inner]
    note: str | None = None
    mood: str = "calm"


def _req(**kw):
    tool = ToolSpec("get_profile", "Read the workspace profile", {"type": "object", "properties": {},
                                                                  "required": [], "additionalProperties": False})
    return LLMRequest(system="SYS", tools=[tool], output_schema=strict_schema(Out), output_name="out",
                      messages=[LLMMessage("user", "hi"),
                                LLMMessage("assistant", None, tool_calls=[ToolCall("c1", "get_profile", {})]),
                                LLMMessage("tool", '{"ok":true}', tool_call_id="c1", tool_name="get_profile"),
                                LLMMessage("tool", '{"ok":2}', tool_call_id="c2", tool_name="get_profile")], **kw)


def test_strict_schema_shape():
    s = strict_schema(Out)
    assert s["additionalProperties"] is False and s["required"] == ["title", "items", "note", "mood"]
    inner = s["properties"]["items"]["items"]
    assert inner["additionalProperties"] is False and inner["required"] == ["label"]
    assert "maxLength" not in json.dumps(s) and "$ref" not in json.dumps(s) and "$defs" not in s
    assert "max length 40" in inner["properties"]["label"]["description"]
    assert s["properties"]["note"]["type"] == ["string", "null"]
    assert schema_stats(s) == {"unions": 1, "properties": 5}


@pytest.fixture
def keys(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "openai_api_key", SecretStr("sk-test"))
    monkeypatch.setattr(s, "anthropic_api_key", SecretStr("ak-test"))
    monkeypatch.setattr(s, "ai_model", "std-model")
    monkeypatch.setattr(s, "ai_model_fast", "fast-model")


async def test_openai_request_and_tool_call_response(keys):
    seen = {}

    def handler(request: httpx.Request):
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["authorization"], json.loads(request.content)
        return httpx.Response(200, json={"model": "fast-model", "usage": {"prompt_tokens": 11, "completion_tokens": 7},
                                         "choices": [{"finish_reason": "tool_calls", "message": {"content": None,
                                                      "tool_calls": [{"id": "t9", "type": "function", "function": {
                                                          "name": "search_context", "arguments": '{"query":"tone"}'}}]}}]})
    r = await OpenAIProvider(httpx.MockTransport(handler)).generate(_req(tier="fast"))
    b = seen["body"]
    assert seen["url"].endswith("/chat/completions") and seen["auth"] == "Bearer sk-test"
    assert b["model"] == "fast-model" and b["messages"][0] == {"role": "system", "content": "SYS"}
    assert b["response_format"]["type"] == "json_schema" and b["response_format"]["json_schema"]["strict"] is True
    assert b["tools"][0]["type"] == "function" and b["tools"][0]["function"]["strict"] is True
    assert b["messages"][2]["tool_calls"][0]["function"] == {"name": "get_profile", "arguments": "{}"}
    assert b["messages"][3] == {"role": "tool", "tool_call_id": "c1", "content": '{"ok":true}'}
    assert r.stop == "tool_calls" and r.tool_calls[0].arguments == {"query": "tone"}
    assert (r.tokens_in, r.tokens_out) == (11, 7)


async def test_openai_refusal_bad_json_and_errors(keys):
    def refusal(_):
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": None,
                                                                                            "refusal": "can't help"}}]})
    r = await OpenAIProvider(httpx.MockTransport(refusal)).generate(_req())
    assert r.stop == "refusal" and r.refusal == "can't help"

    def bad_args(_):
        return httpx.Response(200, json={"choices": [{"message": {"tool_calls": [{"id": "x", "function": {
            "name": "t", "arguments": "{not json"}}]}}]})
    r = await OpenAIProvider(httpx.MockTransport(bad_args)).generate(_req())
    assert r.tool_calls[0].arguments is None and r.tool_calls[0].raw_arguments == "{not json"

    with pytest.raises(ProviderError) as e:
        await OpenAIProvider(httpx.MockTransport(lambda _: httpx.Response(429, json={}))).generate(_req())
    assert e.value.code == "provider_http_429" and e.value.retryable


async def test_anthropic_request_shape_and_parsing(keys):
    seen = {}

    def handler(request: httpx.Request):
        seen["headers"], seen["body"] = request.headers, json.loads(request.content)
        return httpx.Response(200, json={"model": "std-model", "stop_reason": "end_turn",
                                         "usage": {"input_tokens": 20, "output_tokens": 5},
                                         "content": [{"type": "text", "text": '{"title":"x","items":[],"note":null,"mood":"calm"}'}]})
    r = await AnthropicProvider(httpx.MockTransport(handler)).generate(_req())
    b, h = seen["body"], seen["headers"]
    assert h["x-api-key"] == "ak-test" and h["anthropic-version"] == "2023-06-01" and "anthropic-beta" not in h
    assert b["system"] == "SYS" and b["output_config"]["format"]["type"] == "json_schema"
    assert "output_format" not in b
    assert b["tools"][0]["strict"] is True and "input_schema" in b["tools"][0]
    assert b["messages"][1]["content"][0] == {"type": "tool_use", "id": "c1", "name": "get_profile", "input": {}}
    # both tool results merged into one user turn
    assert b["messages"][2]["role"] == "user" and [x["tool_use_id"] for x in b["messages"][2]["content"]] == ["c1", "c2"]
    assert r.stop == "end" and json.loads(r.text)["title"] == "x" and r.tokens_in == 20


async def test_anthropic_tool_use_refusal_and_limits(keys):
    def tool_use(_):
        return httpx.Response(200, json={"stop_reason": "tool_use", "content": [
            {"type": "text", "text": "checking"}, {"type": "tool_use", "id": "tu1", "name": "read_document",
                                                   "input": {"document_id": "abc"}}]})
    r = await AnthropicProvider(httpx.MockTransport(tool_use)).generate(_req())
    assert r.stop == "tool_calls" and r.tool_calls[0].arguments == {"document_id": "abc"}

    r = await AnthropicProvider(httpx.MockTransport(lambda _: httpx.Response(200, json={
        "stop_reason": "refusal", "content": [{"type": "text", "text": "no"}]}))).generate(_req())
    assert r.stop == "refusal"

    many = _req()
    many.tools = many.tools * 21
    with pytest.raises(ProviderError) as e:
        await AnthropicProvider(httpx.MockTransport(lambda _: httpx.Response(200))).generate(many)
    assert e.value.code == "too_many_tools"


async def test_unconfigured_provider_fails_closed(monkeypatch):
    monkeypatch.setattr(get_settings(), "openai_api_key", None)
    with pytest.raises(ProviderError) as e:
        await OpenAIProvider().generate(_req())
    assert e.value.code == "provider_not_configured"


async def test_hash_embedder_is_deterministic_and_normalised():
    e = HashEmbedder(1536)
    a, b, c = await e.embed(["brand voice is playful", "brand voice is playful", "invoice due friday"])
    assert a == b and len(a) == 1536 and abs(sum(x * x for x in a) - 1) < 1e-9
    assert sum(x * y for x, y in zip(a, b)) > sum(x * y for x, y in zip(a, c))
