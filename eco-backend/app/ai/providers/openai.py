"""OpenAI Chat Completions adapter.

Wire format used (checked 2026-11-10 against OpenAI's Structured Outputs guide):
- structured answers: ``response_format = {"type": "json_schema", "json_schema": {"name", "schema", "strict": true}}``
- tools: ``{"type": "function", "function": {"name", "description", "parameters", "strict": true}}``
- a safety refusal arrives in ``message.refusal`` instead of schema-shaped content.
Model names, the token-limit parameter and data-retention settings should be re-checked when choosing a model.
"""
from __future__ import annotations

import json
import time

import httpx

from app.ai.providers.base import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    ProviderError,
    Tier,
    ToolCall,
)
from app.core.config import get_settings


def build_payload(req: LLMRequest, model: str) -> dict:
    messages: list[dict] = [{"role": "system", "content": req.system}]
    for m in req.messages:
        messages.append(_message(m))
    body: dict = {"model": model, "messages": messages, "max_completion_tokens": req.max_tokens}
    if req.temperature is not None:
        body["temperature"] = req.temperature
    if req.tools:
        body["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                           "parameters": t.parameters, "strict": True}}
                         for t in req.tools]
    if req.output_schema is not None:
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": req.output_name, "schema": req.output_schema,
                                                   "strict": True}}
    return body


def _message(m: LLMMessage) -> dict:
    if m.role == "tool":
        return {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content or ""}
    if m.role == "assistant" and m.tool_calls:
        return {"role": "assistant", "content": m.content,
                "tool_calls": [{"id": c.id, "type": "function",
                                "function": {"name": c.name,
                                             "arguments": c.raw_arguments or json.dumps(c.arguments or {})}}
                               for c in m.tool_calls]}
    return {"role": m.role, "content": m.content or ""}


def parse_response(body: dict, latency_ms: int, fallback_model: str) -> LLMResponse:
    choice = (body.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    calls = []
    for c in msg.get("tool_calls") or []:
        raw = (c.get("function") or {}).get("arguments") or ""
        try:
            args = json.loads(raw) if raw else {}
            if not isinstance(args, dict):
                args = None
        except json.JSONDecodeError:
            args = None
        calls.append(ToolCall(id=c.get("id", ""), name=(c.get("function") or {}).get("name", ""), arguments=args,
                              raw_arguments=raw))
    finish = choice.get("finish_reason")
    if msg.get("refusal"):
        stop = "refusal"
    elif calls:
        stop = "tool_calls"
    elif finish == "length":
        stop = "max_tokens"
    else:
        stop = "end"
    usage = body.get("usage") or {}
    return LLMResponse(text=msg.get("content") or "", tool_calls=calls, stop=stop,
                       model=body.get("model", fallback_model), tokens_in=int(usage.get("prompt_tokens", 0)),
                       tokens_out=int(usage.get("completion_tokens", 0)), latency_ms=latency_ms,
                       refusal=msg.get("refusal"))


class OpenAIProvider:
    name = "openai"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport  # tests inject httpx.MockTransport; production uses the network

    def model_for(self, tier: Tier) -> str:
        s = get_settings()
        return (s.ai_model_fast or s.ai_model) if tier == "fast" else s.ai_model

    async def generate(self, req: LLMRequest) -> LLMResponse:
        s = get_settings()
        if s.openai_api_key is None:
            raise ProviderError("provider_not_configured")
        model = self.model_for(req.tier)
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(base_url=s.openai_base_url, timeout=s.ai_timeout_seconds,
                                         transport=self._transport) as client:
                r = await client.post("/chat/completions", json=build_payload(req, model),
                                      headers={"Authorization": f"Bearer {s.openai_api_key.get_secret_value()}"})
        except httpx.HTTPError:
            raise ProviderError("provider_unreachable", retryable=True) from None
        if r.status_code >= 400:
            raise ProviderError(f"provider_http_{r.status_code}", retryable=r.status_code in (429, 500, 502, 503))
        return parse_response(r.json(), int((time.monotonic() - t0) * 1000), model)
