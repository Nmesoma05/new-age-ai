"""Web research backend interface. No backend ships enabled: choose a search API, check its terms and current
capabilities, then implement ResearchBackend. Until then the researcher agent reports research as unavailable
instead of answering from the model's memory as if it were fresh."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class ResearchBackend(Protocol):
    name: str

    async def search(self, query: str, max_results: int) -> list[SearchResult]: ...


def get_research_backend() -> ResearchBackend | None:
    return None
