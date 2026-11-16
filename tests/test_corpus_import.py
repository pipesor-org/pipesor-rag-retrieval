from dataclasses import replace
from uuid import UUID

import pytest

from pipesor_rag_retrieval.corpus import CorpusImport, ImportAuthorizedCorpus, ImportStatus, InMemoryCorpusStore
from pipesor_rag_retrieval.domain import AuthorizationScope, CorpusKind
from pipesor_rag_retrieval.infrastructure import DeterministicEmbeddingProvider


def request(version: str = "v1", content: str = "Synthetic authorized procedure") -> CorpusImport:
    return CorpusImport(
        source_id="runbook/worker",
        source_version=version,
        title="Worker runbook",
        provenance="synthetic://runbooks/worker",
        authorization_reference="approval://CAB-42",
        corpus_kind=CorpusKind.AUTHORIZED_RESPONSE_PROCEDURES,
        scope=AuthorizationScope(UUID("11111111-1111-4111-8111-111111111111"), "20", "10", None, "scope-1"),
        chunks=(content,),
        correlation_id="corr-1",
    )


def test_import_is_idempotent_and_replaces_new_version() -> None:
    store = InMemoryCorpusStore()
    importer = ImportAuthorizedCorpus(store, DeterministicEmbeddingProvider())
    assert importer.execute(request()) == ImportStatus.CREATED
    assert importer.execute(request()) == ImportStatus.UNCHANGED
    assert importer.execute(request(version="v2")) == ImportStatus.REPLACED


def test_same_version_with_different_content_conflicts() -> None:
    store = InMemoryCorpusStore()
    importer = ImportAuthorizedCorpus(store, DeterministicEmbeddingProvider())
    importer.execute(request())
    with pytest.raises(ValueError, match="different content"):
        importer.execute(request(content="Changed"))


def test_evaluation_material_is_rejected() -> None:
    store = InMemoryCorpusStore()
    importer = ImportAuthorizedCorpus(store, DeterministicEmbeddingProvider())
    candidate = request()
    forbidden = replace(candidate, evaluation_material=True)
    with pytest.raises(ValueError, match="evaluation material"):
        importer.execute(forbidden)
