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

