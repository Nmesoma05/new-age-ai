"""Provider-neutral types. Agents and the orchestrator only ever see these, so the model vendor can change
without touching application code. Each adapter translates to and from one vendor's wire format."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Tier = Literal["fast", "standard"]
StopReason = Literal["end", "tool_calls", "max_tokens", "refusal"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # strict JSON schema (see schema.strict_schema)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] | None  # None when the model produced unparseable JSON
    raw_arguments: str = ""


@dataclass
class LLMMessage:
    role: Literal["user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)  # assistant turns that requested tools
    tool_call_id: str | None = None  # tool turns
    tool_name: str | None = None
    is_error: bool = False


@dataclass
class LLMRequest:
    system: str
    messages: list[LLMMessage]
    tier: Tier = "standard"
    tools: list[ToolSpec] = field(default_factory=list)
    output_schema: dict[str, Any] | None = None  # strict JSON schema for the final answer
    output_name: str = "output"
    max_tokens: int = 2000
    temperature: float | None = None
    metadata: dict[str, str] = field(default_factory=dict)  # agent name, run id: for logs, never sent as prompt


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    stop: StopReason
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    refusal: str | None = None


class ProviderError(Exception):
    """Transport or vendor failure. `code` is safe to store and show; no vendor payload is kept."""

    def __init__(self, code: str, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class LLMProvider(Protocol):
    name: str

    def model_for(self, tier: Tier) -> str: ...

    async def generate(self, request: LLMRequest) -> LLMResponse: ...


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dims: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
