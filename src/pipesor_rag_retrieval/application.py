from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from .domain import AuthorizationScope, CorpusKind, cosine_similarity
from .ports import EmbeddingProvider, KnowledgeRepository


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    correlation_id: str
    query: str
    scope: AuthorizationScope
    allowed_corpus_kinds: frozenset[CorpusKind]
    top_k: int


@dataclass(frozen=True, slots=True)
class RetrievalMatch:
    chunk_id: UUID
    document_id: UUID
    corpus_kind: CorpusKind
    title: str
    content: str
    provenance: str
    score: float


class RetrieveAuthorizedKnowledge:
    def __init__(self, repository: KnowledgeRepository, embeddings: EmbeddingProvider) -> None:
        self._repository = repository
        self._embeddings = embeddings

    def execute(self, query: RetrievalQuery) -> tuple[RetrievalMatch, ...]:
        query_vector = self._embeddings.embed(query.query)
        matches: list[RetrievalMatch] = []
        for chunk in self._repository.candidates(query.scope):
            if not query.scope.permits(chunk.scope):
                continue
            if chunk.corpus_kind not in query.allowed_corpus_kinds:
                continue
            score = cosine_similarity(query_vector, chunk.embedding)
            matches.append(
                RetrievalMatch(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    corpus_kind=chunk.corpus_kind,
                    title=chunk.title,
                    content=chunk.content,
                    provenance=chunk.provenance,
                    score=score,
                )
            )
        matches.sort(key=lambda item: (-item.score, str(item.chunk_id)))
        return tuple(matches[: query.top_k])

