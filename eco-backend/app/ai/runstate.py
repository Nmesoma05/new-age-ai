"""Mutable state for one orchestrated request, shared by every agent and tool in it."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.ai.safety import new_boundary


@dataclass
class LLMCallLog:
    agent: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    ok: bool
    error_code: str | None = None


@dataclass
class ToolLog:
    agent: str
    tool: str
    args: dict
    status: str  # ok | error | denied
    error_code: str | None
    untrusted: bool
    result_meta: dict
    latency_ms: int


@dataclass
class Proposal:
    id: uuid.UUID
    kind: str
    title: str


@dataclass
class RunState:
    user_message: str
    run_id: uuid.UUID = field(default_factory=uuid.uuid4)
    boundary: str = field(default_factory=new_boundary)
    refs_seen: set[str] = field(default_factory=set)     # everything retrieved this run (for citation checks)
    urls_seen: set[str] = field(default_factory=set)     # URLs from research results + the user's message
    profile_refs: dict[str, str] = field(default_factory=dict)  # ref -> text, for grounding checks
    tainted: bool = False                                 # untrusted content entered a prompt
    injection_flags: list[dict] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)
    llm_calls: list[LLMCallLog] = field(default_factory=list)
    tool_logs: list[ToolLog] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    corpus: list[str] = field(default_factory=list)      # all text the agents were shown (for number checks)
    doc_choices: set[str] = field(default_factory=set)   # document ids the router may pick from
    writes_run_row: bool = False  # the orchestrator will insert agent_runs(run_id) before commit

    def flag(self, source: str, flags: list[str]) -> None:
        if flags:
            self.injection_flags.append({"source": source, "patterns": flags})

    @property
    def tokens(self) -> tuple[int, int]:
        return sum(c.tokens_in for c in self.llm_calls), sum(c.tokens_out for c in self.llm_calls)
