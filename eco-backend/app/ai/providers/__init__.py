"""Provider factory. FastAPI resolves these through Depends, so tests can override them in one place."""
from __future__ import annotations

from app.ai.providers.base import EmbeddingProvider, LLMProvider
from app.core.config import get_settings


def get_llm_provider() -> LLMProvider:
    s = get_settings()
    if s.ai_provider == "anthropic":
        from app.ai.providers.anthropic import AnthropicProvider
        return AnthropicProvider()
    from app.ai.providers.openai import OpenAIProvider
    return OpenAIProvider()


def get_embedder() -> EmbeddingProvider | None:
    s = get_settings()
    if s.embedding_provider == "openai":
        from app.ai.providers.embeddings import OpenAIEmbedder
        return OpenAIEmbedder()
    if s.embedding_provider == "hash_dev_only":
        from app.ai.providers.embeddings import HashEmbedder
        return HashEmbedder(s.embedding_dims)
    return None
