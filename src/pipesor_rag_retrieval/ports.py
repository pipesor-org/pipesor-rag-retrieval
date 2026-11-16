from __future__ import annotations

from typing import Protocol

from .domain import AuthorizationScope, KnowledgeChunk


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> tuple[float, ...]: ...


class KnowledgeRepository(Protocol):
    def candidates(self, scope: AuthorizationScope) -> tuple[KnowledgeChunk, ...]: ...

    def ready(self) -> bool: ...

