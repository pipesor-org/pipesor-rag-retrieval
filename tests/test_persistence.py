from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from pipesor_rag_retrieval.domain import AuthorizationScope, CorpusKind
from pipesor_rag_retrieval.persistence import (
    KnowledgeChunkRecord,
    KnowledgeDocumentRecord,
    PostgreSQLKnowledgeRepository,
)


TENANT = UUID("11111111-1111-4111-8111-111111111111")
PIPELINE = UUID("22222222-2222-4222-8222-222222222222")


class Rows:
    def __init__(self, values: list[tuple[KnowledgeChunkRecord, KnowledgeDocumentRecord, float]]) -> None:
        self.values = values

    def all(self) -> list[tuple[KnowledgeChunkRecord, KnowledgeDocumentRecord, float]]:
        return self.values


class FakeSession:
    def __init__(self, values: list[tuple[KnowledgeChunkRecord, KnowledgeDocumentRecord, float]]) -> None:
        self.values = values
        self.statement = None
        self.statements = []

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, statement: object) -> Rows:
        self.statements.append(statement)
        self.statement = statement
        return Rows([] if str(statement).startswith("SET LOCAL") else self.values)


def records() -> tuple[KnowledgeChunkRecord, KnowledgeDocumentRecord]:
    now = datetime.now(UTC)
    document = KnowledgeDocumentRecord(
        id=UUID("44444444-4444-4444-8444-444444444444"),
        corpus_kind=CorpusKind.AUTHORIZED_TECHNICAL_DOCUMENTATION.value,
        title="Synthetic runbook",
        provenance="synthetic://runbook",
        tenant_id=TENANT,
        github_installation_id="20",
        github_repository_id="10",
        pipeline_id=PIPELINE,
        scope_revision="scope-1",
        source_id="runbook/worker",
        source_version="v1",
        content_hash="0" * 64,
        authorization_reference="approval://CAB-42",
        active=True,
        correlation_id="corr-1",
        created_at=now,
    )
    chunk = KnowledgeChunkRecord(
        id=UUID("33333333-3333-4333-8333-333333333333"),
        document_id=document.id,
        chunk_index=0,
        content="Synthetic content",
        provenance="synthetic://runbook#0",
        embedding=[0.1, 0.2],
        embedding_model="text-embedding-3-small",
        embedding_model_version="simulated-v1",
        correlation_id="corr-1",
        created_at=now,
    )
    return chunk, document


def test_repository_maps_authorized_rows_and_provenance() -> None:
    fake = FakeSession([(*records(), 0.25)])
    repository = PostgreSQLKnowledgeRepository(lambda: fake)
    scope = AuthorizationScope(TENANT, "20", "10", PIPELINE, "scope-1")

    result = repository.search(
        scope,
        tuple(0.1 for _ in range(1536)),
        "text-embedding-3-small",
        "simulated-v1",
        frozenset({CorpusKind.AUTHORIZED_TECHNICAL_DOCUMENTATION}),
        5,
    )

    assert result[0].chunk.provenance == "synthetic://runbook#0"
    assert result[0].chunk.scope == scope
    assert result[0].score == 0.75
    compiled = fake.statement.compile(dialect=postgresql.dialect())
    assert "tenant_id" in str(compiled)
    assert "scope_revision" in str(compiled)
    assert "ORDER BY" in str(compiled)
    assert "LIMIT" in str(compiled)
    assert any("hnsw.ef_search" in str(statement) for statement in fake.statements)


def test_repository_requires_positive_query_controls() -> None:
    with pytest.raises(ValueError, match="query controls"):
        PostgreSQLKnowledgeRepository(lambda: FakeSession([]), hnsw_ef_search=0)

