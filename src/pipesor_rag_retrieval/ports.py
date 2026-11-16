from __future__ import annotations

from typing import Protocol

from .domain import AuthorizationScope, KnowledgeChunk


class EmbeddingProvider(Protocol):
    model_name: str
    model_version: str
    dimension: int

    def embed(self, text: str) -> tuple[float, ...]: ...


class KnowledgeRepository(Protocol):
    def candidates(
        self,
        scope: AuthorizationScope,
        query_embedding: tuple[float, ...],
        embedding_model: str,
        embedding_model_version: str,
    ) -> tuple[KnowledgeChunk, ...]: ...

    def ready(self) -> bool: ...

