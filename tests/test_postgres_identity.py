from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pipesor_rag_retrieval import bootstrap
from pipesor_rag_retrieval.configuration import Settings


def hosted_settings(url: str) -> Settings:
    return Settings(
        runtime_environment="azure",
        host="0.0.0.0",
        port=8080,
        authentication_mode="entra",
        entra_tenant_id="11111111-1111-4111-8111-111111111111",
        entra_audience="22222222-2222-4222-8222-222222222222",
        entra_recommendation_client_id="33333333-3333-4333-8333-333333333333",
        storage_backend="postgresql",
        database_url=url,
        embedding_backend="azure_openai",
        azure_openai_endpoint="https://ai-pipesor-dev-04f339b7.services.ai.azure.com",
        azure_openai_deployment="pipesor-dev-embeddings",
        embedding_model_version="2026-11",
    )


def test_new_physical_connections_obtain_managed_identity_tokens(monkeypatch) -> None:
    credential = Mock()
    credential.get_token.side_effect = [
        SimpleNamespace(token="first-synthetic-token"),
        SimpleNamespace(token="second-synthetic-token"),
    ]
    monkeypatch.setattr(bootstrap, "ManagedIdentityCredential", lambda: credential)
    engine = bootstrap.build_postgresql_engine(
        hosted_settings("postgresql+psycopg://rag@app.postgres.database.azure.com/pipesor")
    )

    # Stop at the DBAPI boundary without contacting either Azure or PostgreSQL.
    connect = Mock(side_effect=RuntimeError("stop before network"))
    monkeypatch.setattr(engine.dialect, "connect", connect)
    try:
        for _ in range(2):
            with pytest.raises(RuntimeError, match="stop before network"):
                engine.connect()
        assert engine.url.password is None
        assert [call.kwargs["password"] for call in connect.call_args_list] == [
            "first-synthetic-token", "second-synthetic-token",
        ]
        for call in connect.call_args_list:
            assert call.kwargs["sslmode"] == "verify-full"
            assert call.kwargs["sslrootcert"] == "system"
            assert call.kwargs["host"] == "app.postgres.database.azure.com"
        assert [call.args for call in credential.get_token.call_args_list] == [
            ("https://ossrdbms-aad.database.windows.net/.default",),
        ] * 2
    finally:
        engine.dispose()


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://rag:sample@app.postgres.database.azure.com/pipesor",
    "postgresql+psycopg://rag@app.postgres.database.azure.com/pipesor?host=other.example",
    "postgresql+psycopg://rag@other.example/pipesor",
    "postgresql+psycopg://rag@other.example,app.postgres.database.azure.com/pipesor",
])
def test_hosted_url_cannot_supply_credentials_or_override_target(url: str) -> None:
    with pytest.raises(ValueError, match="password-free Azure PostgreSQL URL"):
        bootstrap.build_postgresql_engine(hosted_settings(url))
