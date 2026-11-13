"""Anthropic Messages API adapter.

Wire format used (checked 2026-11-10 against platform.claude.com "Structured outputs" and "Define tools"):
- structured answers: ``output_config = {"format": {"type": "json_schema", "schema": ...}}``; no beta header
  is needed (the older ``output_format`` parameter is deprecated)
- tools: ``{"name", "description", "input_schema", "strict": true}``; at most 20 strict tools per request
- ``stop_reason`` of ``refusal`` or ``max_tokens`` means the JSON may not match the schema
- tool results go back as ``tool_result`` blocks inside a user turn
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

MAX_STRICT_TOOLS = 20


def build_payload(req: LLMRequest, model: str) -> dict:
    if len(req.tools) > MAX_STRICT_TOOLS:
        raise ProviderError("too_many_tools")
    body: dict = {"model": model, "max_tokens": req.max_tokens, "system": req.system,
                  "messages": _messages(req.messages)}
    if req.temperature is not None:
        body["temperature"] = req.temperature
    if req.tools:
        body["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.parameters, "strict": True}
                         for t in req.tools]
    if req.output_schema is not None:
        body["output_config"] = {"format": {"type": "json_schema", "schema": req.output_schema}}
    return body


def _messages(msgs: list[LLMMessage]) -> list[dict]:
    out: list[dict] = []
    for m in msgs:
        if m.role == "tool":
            block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content or ""}
            if m.is_error:
                block["is_error"] = True
            # consecutive tool results share one user turn
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list) and \
                    all(b.get("type") == "tool_result" for b in out[-1]["content"]):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
        elif m.role == "assistant" and m.tool_calls:
            blocks: list[dict] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments or {}}
                       for c in m.tool_calls]
            out.append({"role": "assistant", "content": blocks})
        else:
            out.append({"role": m.role, "content": m.content or ""})
    return out


def parse_response(body: dict, latency_ms: int, fallback_model: str) -> LLMResponse:
    text_parts, calls = [], []
    for b in body.get("content") or []:
        if b.get("type") == "text":
            text_parts.append(b.get("text", ""))
        elif b.get("type") == "tool_use":
            inp = b.get("input")
            calls.append(ToolCall(id=b.get("id", ""), name=b.get("name", ""),
                                  arguments=inp if isinstance(inp, dict) else None,
                                  raw_arguments=json.dumps(inp) if inp is not None else ""))
    reason = body.get("stop_reason")
    stop = {"tool_use": "tool_calls", "max_tokens": "max_tokens", "refusal": "refusal"}.get(reason, "end")
    if calls and stop == "end":
        stop = "tool_calls"
    usage = body.get("usage") or {}
    text = "".join(text_parts)
    return LLMResponse(text=text, tool_calls=calls, stop=stop, model=body.get("model", fallback_model),
                       tokens_in=int(usage.get("input_tokens", 0)), tokens_out=int(usage.get("output_tokens", 0)),
                       latency_ms=latency_ms, refusal=text if stop == "refusal" else None)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    def model_for(self, tier: Tier) -> str:
        s = get_settings()
        return (s.ai_model_fast or s.ai_model) if tier == "fast" else s.ai_model

    async def generate(self, req: LLMRequest) -> LLMResponse:
        s = get_settings()
        if s.anthropic_api_key is None:
            raise ProviderError("provider_not_configured")
        model = self.model_for(req.tier)
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(base_url=s.anthropic_base_url, timeout=s.ai_timeout_seconds,
                                         transport=self._transport) as client:
                r = await client.post("/messages", json=build_payload(req, model),
                                      headers={"x-api-key": s.anthropic_api_key.get_secret_value(),
                                               "anthropic-version": s.anthropic_version})
        except httpx.HTTPError:
            raise ProviderError("provider_unreachable", retryable=True) from None
        if r.status_code >= 400:
            raise ProviderError(f"provider_http_{r.status_code}", retryable=r.status_code in (429, 500, 529))
        return parse_response(r.json(), int((time.monotonic() - t0) * 1000), model)
