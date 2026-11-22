import pytest
from pydantic import ValidationError

from pipesor_rag_retrieval.configuration import Settings


def test_memory_storage_is_safe_default() -> None:
    settings = Settings()
    assert settings.storage_backend == "memory"
    assert settings.database_url is None


def test_postgresql_requires_database_url() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(storage_backend="postgresql")


def test_database_url_is_secret() -> None:
    settings = Settings(
        storage_backend="postgresql",
        database_url="postgresql+psycopg://user:secret@database/knowledge",
    )
    assert "secret" not in repr(settings)


def test_test_backends_are_forbidden_outside_automated_tests() -> None:
    with pytest.raises(ValidationError, match="runtime requires PostgreSQL"):
        Settings(runtime_environment="local")


def test_entra_mode_requires_all_canonical_identifiers() -> None:
    with pytest.raises(ValidationError, match="tenant, audience and Recommendation"):
        Settings(authentication_mode="entra")


def test_entra_mode_accepts_complete_single_tenant_contract() -> None:
    settings = Settings(
        authentication_mode="entra",
        entra_tenant_id="11111111-1111-4111-8111-111111111111",
        entra_audience="22222222-2222-4222-8222-222222222222",
        entra_recommendation_client_id="33333333-3333-4333-8333-333333333333",
    )
    assert settings.entra_required_role == "Rag.Query"


def test_azure_embeddings_require_https_endpoint_and_deployment() -> None:
    with pytest.raises(ValidationError, match="endpoint and deployment"):
        Settings(embedding_backend="azure_openai")
    with pytest.raises(ValidationError, match="must use HTTPS"):
        Settings(
            embedding_backend="azure_openai",
            azure_openai_endpoint="http://foundry.invalid",
            azure_openai_deployment="pipesor-dev-embeddings",
            embedding_model_version="2026-11",
        )


def test_approved_embedding_contract_is_dimensioned() -> None:
    settings = Settings()
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.embedding_dimension == 1536
    assert settings.embedding_timeout_seconds == 15
    assert settings.embedding_max_retries == 2

