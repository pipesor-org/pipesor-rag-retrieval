from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .domain import AuthorizationScope, KnowledgeChunk


@dataclass(frozen=True, slots=True)
class RankedKnowledgeChunk:
    chunk: KnowledgeChunk
    score: float


class EmbeddingProvider(Protocol):
    model_name: str
    model_version: str
    dimension: int

    def embed(self, text: str) -> tuple[float, ...]: ...


class KnowledgeRepository(Protocol):
    def search(
        self,
        scope: AuthorizationScope,
        query_embedding: tuple[float, ...],
        embedding_model: str,
        embedding_model_version: str,
        allowed_corpus_kinds: frozenset,
        top_k: int,
    ) -> tuple[RankedKnowledgeChunk, ...]: ...

    def ready(self) -> bool: ...

