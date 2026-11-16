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


def test_simulated_authentication_is_forbidden_outside_local_test() -> None:
    with pytest.raises(ValidationError, match="simulated authentication"):
        Settings(runtime_environment="dev")


def test_unimplemented_entra_mode_fails_closed() -> None:
    with pytest.raises(ValidationError, match="Entra authentication is not implemented"):
        Settings(authentication_mode="entra")


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

