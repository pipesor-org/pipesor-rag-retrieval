from uuid import UUID

import pytest

from pipesor_rag_retrieval.application import RetrievalQuery, RetrieveAuthorizedKnowledge
from pipesor_rag_retrieval.domain import AuthorizationScope, CorpusKind, KnowledgeChunk
from pipesor_rag_retrieval.infrastructure import (
    DeterministicEmbeddingProvider,
    InMemoryKnowledgeRepository,
)
from pipesor_rag_retrieval.errors import RetrievalUnavailable

TENANT = UUID("11111111-1111-4111-8111-111111111111")
PIPELINE = UUID("22222222-2222-4222-8222-222222222222")


def scope(repository_id: str = "10", revision: str = "scope-1") -> AuthorizationScope:
    return AuthorizationScope(TENANT, "20", repository_id, PIPELINE, revision)


def chunk(*, repository_id: str = "10", evaluation: bool = False) -> KnowledgeChunk:
    embeddings = DeterministicEmbeddingProvider()
    return KnowledgeChunk(
        id=UUID("33333333-3333-4333-8333-333333333333"),
        document_id=UUID("44444444-4444-4444-8444-444444444444"),
        chunk_index=0,
        corpus_kind=CorpusKind.AUTHORIZED_TECHNICAL_DOCUMENTATION,
        title="Synthetic runbook",
        content="Restart the synthetic worker after verifying its lease.",
        provenance="synthetic://runbooks/worker#restart",
        scope=scope(repository_id),
        embedding=embeddings.embed("worker lease restart"),
        evaluation_material=evaluation,
    )


def query(target_scope: AuthorizationScope) -> RetrievalQuery:
    return RetrievalQuery(
        correlation_id="corr-1",
        query="worker lease restart",
        scope=target_scope,
        allowed_corpus_kinds=frozenset({CorpusKind.AUTHORIZED_TECHNICAL_DOCUMENTATION}),
        top_k=5,
    )


def test_returns_authorized_match_with_provenance() -> None:
    service = RetrieveAuthorizedKnowledge(
        InMemoryKnowledgeRepository((chunk(),)), DeterministicEmbeddingProvider()
    )

    result = service.execute(query(scope()))

    assert len(result) == 1
    assert result[0].provenance == "synthetic://runbooks/worker#restart"


def test_does_not_return_another_repository_scope() -> None:
    service = RetrieveAuthorizedKnowledge(
        InMemoryKnowledgeRepository((chunk(repository_id="11"),)),
        DeterministicEmbeddingProvider(),
    )

    assert service.execute(query(scope(repository_id="10"))) == ()


def test_rejects_evaluation_material_from_corpus() -> None:
    with pytest.raises(ValueError, match="evaluation material"):
        chunk(evaluation=True)


def test_rejects_incompatible_vectors() -> None:
    invalid = KnowledgeChunk(
        id=UUID("33333333-3333-4333-8333-333333333333"),
        document_id=UUID("44444444-4444-4444-8444-444444444444"),
        chunk_index=0,
        corpus_kind=CorpusKind.AUTHORIZED_TECHNICAL_DOCUMENTATION,
        title="Synthetic",
        content="Synthetic content",
        provenance="synthetic://source",
        scope=scope(),
        embedding=(1.0,),
    )
    service = RetrieveAuthorizedKnowledge(
        InMemoryKnowledgeRepository((invalid,)), DeterministicEmbeddingProvider()
    )

    with pytest.raises(RetrievalUnavailable, match="unavailable"):
        service.execute(query(scope()))


@pytest.mark.parametrize("failure", [ValueError("provider response"), (), (float("nan"),) * 1536])
def test_embedding_failure_is_unavailable_even_with_empty_corpus(failure) -> None:
    class InvalidEmbeddingProvider(DeterministicEmbeddingProvider):
        def embed(self, text: str) -> tuple[float, ...]:
            if isinstance(failure, ValueError):
                raise failure
            return failure

    service = RetrieveAuthorizedKnowledge(InMemoryKnowledgeRepository(), InvalidEmbeddingProvider())

    with pytest.raises(RetrievalUnavailable, match="unavailable"):
        service.execute(query(scope()))
