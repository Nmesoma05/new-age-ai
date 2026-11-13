"""Embedding providers for retrieval."""
from __future__ import annotations

import hashlib
import math
import re

import httpx

from app.ai.providers.base import ProviderError
from app.core.config import get_settings

_WORD = re.compile(r"[\w']+", re.UNICODE)


class HashEmbedder:
    """Deterministic feature-hashing embedder (bag of words + bigrams). No network, no learned semantics:
    it only matches shared words. Good enough to exercise the vector path in dev and tests; refused in prod."""

    name = "hash"
    model = "hash-v1"

    def __init__(self, dims: int = 1536):
        self.dims = dims

    def _vec(self, text: str) -> list[float]:
        words = [w.lower() for w in _WORD.findall(text)]
        feats = words + [f"{a} {b}" for a, b in zip(words, words[1:])]
        v = [0.0] * self.dims
        for f in feats:
            h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "big")
            v[h % self.dims] += 1.0 if (h >> 63) & 1 else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]


class OpenAIEmbedder:
    """POST /embeddings. Verify the model's output dimension equals EMBEDDING_DIMS before enabling."""

    name = "openai"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        s = get_settings()
        self.model, self.dims, self._transport = s.embedding_model, s.embedding_dims, transport

    async def embed(self, texts: list[str]) -> list[list[float]]:
        s = get_settings()
        if s.openai_api_key is None:
            raise ProviderError("embeddings_not_configured")
        try:
            async with httpx.AsyncClient(base_url=s.openai_base_url, timeout=s.ai_timeout_seconds,
                                         transport=self._transport) as c:
                r = await c.post("/embeddings", json={"model": self.model, "input": texts},
                                 headers={"Authorization": f"Bearer {s.openai_api_key.get_secret_value()}"})
        except httpx.HTTPError:
            raise ProviderError("provider_unreachable", retryable=True) from None
        if r.status_code >= 400:
            raise ProviderError(f"provider_http_{r.status_code}")
        vecs = [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
        if any(len(v) != self.dims for v in vecs):
            raise ProviderError("embedding_dims_mismatch")
        return vecs
