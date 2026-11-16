from __future__ import annotations

import os
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pipesor_rag_retrieval.application import RetrievalQuery, RetrieveAuthorizedKnowledge
from pipesor_rag_retrieval.corpus import CorpusImport, ImportAuthorizedCorpus, ImportStatus
from pipesor_rag_retrieval.domain import AuthorizationScope, CorpusKind
from pipesor_rag_retrieval.infrastructure import DeterministicEmbeddingProvider
from pipesor_rag_retrieval.persistence import KnowledgeDocumentRecord, PostgreSQLCorpusStore, PostgreSQLKnowledgeRepository

DATABASE_URL = os.environ.get("PIPESOR_RAG_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="disposable PostgreSQL URL not supplied")


def scope(tenant: str, repository: str) -> AuthorizationScope:
    return AuthorizationScope(UUID(tenant), "20", repository, None, "scope-1")


def document(target: AuthorizationScope, version: str = "v1") -> CorpusImport:
    return CorpusImport(
        source_id="runbook/worker",
        source_version=version,
        title="Synthetic worker runbook",
        provenance="synthetic://runbooks/worker",
        authorization_reference="approval://synthetic/CAB-42",
        corpus_kind=CorpusKind.AUTHORIZED_RESPONSE_PROCEDURES,
        scope=target,
        chunks=(f"Synthetic procedure {version}",),
        correlation_id="corr-integration",
    )


def test_real_postgres_import_retrieval_isolation_and_replacement() -> None:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    embeddings = DeterministicEmbeddingProvider()
    importer = ImportAuthorizedCorpus(PostgreSQLCorpusStore(sessions), embeddings)
    repository = PostgreSQLKnowledgeRepository(sessions)
    retrieval = RetrieveAuthorizedKnowledge(repository, embeddings)
    allowed = scope("11111111-1111-4111-8111-111111111111", "10")
    other_tenant = scope("99999999-9999-4999-8999-999999999999", "10")
    other_repository = scope("11111111-1111-4111-8111-111111111111", "11")

    assert repository.ready()
    assert importer.execute(document(allowed)) == ImportStatus.CREATED
    assert importer.execute(document(allowed)) == ImportStatus.UNCHANGED
    query_vector = embeddings.embed("Synthetic procedure")
    assert repository.candidates(other_tenant, query_vector, embeddings.model_name, embeddings.model_version) == ()
    assert repository.candidates(other_repository, query_vector, embeddings.model_name, embeddings.model_version) == ()
    query = RetrievalQuery(
        correlation_id="corr-integration",
        query="Synthetic procedure",
        scope=allowed,
        allowed_corpus_kinds=frozenset({CorpusKind.AUTHORIZED_RESPONSE_PROCEDURES}),
        top_k=5,
    )
    assert len(retrieval.execute(query)) == 1
    assert importer.execute(document(allowed, "v2")) == ImportStatus.REPLACED
    assert len(retrieval.execute(query)) == 1
    with sessions() as session:
        states = session.scalars(
            select(KnowledgeDocumentRecord.active).order_by(KnowledgeDocumentRecord.source_version)
        ).all()
    assert states == [False, True]

