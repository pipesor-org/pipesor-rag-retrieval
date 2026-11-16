from __future__ import annotations

import hashlib

from .domain import AuthorizationScope, KnowledgeChunk


class DeterministicEmbeddingProvider:
    """Test/local adapter only; it is not a semantic production embedding model."""

    dimension = 16

    def embed(self, text: str) -> tuple[float, ...]:
        if not text.strip():
            raise ValueError("query must be non-empty")
        digest = hashlib.sha256(text.casefold().encode("utf-8")).digest()
        return tuple((digest[index] - 127.5) / 127.5 for index in range(self.dimension))


class InMemoryKnowledgeRepository:
    def __init__(self, chunks: tuple[KnowledgeChunk, ...] = ()) -> None:
        self._chunks = chunks

    def candidates(self, scope: AuthorizationScope) -> tuple[KnowledgeChunk, ...]:
        return tuple(chunk for chunk in self._chunks if scope.permits(chunk.scope))

    def ready(self) -> bool:
        return True

