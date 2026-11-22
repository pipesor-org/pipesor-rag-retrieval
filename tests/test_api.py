from uuid import UUID

from fastapi.testclient import TestClient

from pipesor_rag_retrieval.api import create_app
from pipesor_rag_retrieval.application import RetrieveAuthorizedKnowledge
from pipesor_rag_retrieval.domain import AuthorizationScope, CorpusKind, KnowledgeChunk
from pipesor_rag_retrieval.infrastructure import (
    DeterministicEmbeddingProvider,
    InMemoryKnowledgeRepository,
)


def payload() -> dict[str, object]:
    return {
        "contract_version": "1.0",
        "correlation_id": "corr-1",
        "query": "worker lease restart",
        "authorization_scope": {
            "tenant_id": "11111111-1111-4111-8111-111111111111",
            "github_installation_id": "20",
            "github_repository_id": "10",
            "pipeline_id": "22222222-2222-4222-8222-222222222222",
            "scope_revision": "scope-1",
        },
        "allowed_corpus_kinds": ["authorized_technical_documentation"],
        "top_k": 5,
    }


def client(with_match: bool = False) -> TestClient:
    embeddings = DeterministicEmbeddingProvider()
    chunks: tuple[KnowledgeChunk, ...] = ()
    if with_match:
        chunks = (
            KnowledgeChunk(
                id=UUID("33333333-3333-4333-8333-333333333333"),
                document_id=UUID("44444444-4444-4444-8444-444444444444"),
                chunk_index=0,
                corpus_kind=CorpusKind.AUTHORIZED_TECHNICAL_DOCUMENTATION,
                title="Synthetic runbook",
                content="Restart the synthetic worker after verifying its lease.",
                provenance="synthetic://runbooks/worker#restart",
                scope=AuthorizationScope(
                    UUID("11111111-1111-4111-8111-111111111111"),
                    "20",
                    "10",
                    UUID("22222222-2222-4222-8222-222222222222"),
                    "scope-1",
                ),
                embedding=embeddings.embed("worker lease restart"),
            ),
        )
    service = RetrieveAuthorizedKnowledge(InMemoryKnowledgeRepository(chunks), embeddings)
    return TestClient(create_app(service))


def test_requires_internal_caller() -> None:
    response = client().post("/internal/v1/retrieval/query", json=payload())
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["detail"] == "Caller is not authorized"


def test_openapi_contract_documents_internal_security_without_runtime_endpoint() -> None:
    api = create_app()
    schema = api.openapi()

    assert TestClient(api).get("/openapi.json").status_code == 404
    operation = schema["paths"]["/internal/v1/retrieval/query"]["post"]
    assert operation["security"] == [{"SimulatedInternalCaller": []}]
    assert set(operation["responses"]) >= {"200", "403", "422", "503"}
    assert schema["components"]["securitySchemes"]["SimulatedInternalCaller"]["name"] == "X-Pipesor-Caller"


def test_returns_explicit_no_match() -> None:
    response = client().post(
        "/internal/v1/retrieval/query",
        headers={"X-Pipesor-Caller": "recommendation_service"},
        json=payload(),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "no_match"
    assert response.json()["matches"] == []


def test_returns_match_and_provenance() -> None:
    response = client(with_match=True).post(
        "/internal/v1/retrieval/query",
        headers={"X-Pipesor-Caller": "recommendation_service"},
        json=payload(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "matches"
    assert body["matches"][0]["provenance"] == "synthetic://runbooks/worker#restart"


def test_rejects_unknown_contract_fields() -> None:
    request = payload()
    request["unexpected"] = "value"
    response = client().post(
        "/internal/v1/retrieval/query",
        headers={"X-Pipesor-Caller": "recommendation_service"},
        json=request,
    )
    assert response.status_code == 422


def test_health_endpoints() -> None:
    api = client()
    assert api.get("/health/live").json() == {"status": "alive"}
    assert api.get("/health/ready").json() == {"status": "ready"}


def test_rejects_oversized_request_before_parsing() -> None:
    response = client().post(
        "/internal/v1/retrieval/query",
        headers={"content-length": "70000", "X-Pipesor-Caller": "recommendation_service"},
        content=b"{}",
    )
    assert response.status_code == 413
    assert response.json()["detail"] == "request_too_large"

