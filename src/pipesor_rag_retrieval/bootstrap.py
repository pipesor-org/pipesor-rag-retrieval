from __future__ import annotations

import os
import re

from azure.identity import ManagedIdentityCredential
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import sessionmaker

from .application import RetrieveAuthorizedKnowledge
from .configuration import Settings
from .infrastructure import AzureOpenAIEmbeddingProvider, DeterministicEmbeddingProvider, InMemoryKnowledgeRepository
from .ports import EmbeddingProvider
from .persistence import PostgreSQLKnowledgeRepository


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    return (
        AzureOpenAIEmbeddingProvider(
            endpoint=settings.azure_openai_endpoint or "",
            deployment=settings.azure_openai_deployment or "",
            model_version=settings.embedding_model_version,
            timeout_seconds=settings.embedding_timeout_seconds,
            max_retries=settings.embedding_max_retries,
        )
        if settings.embedding_backend == "azure_openai"
        else DeterministicEmbeddingProvider()
    )


SYSTEM_CA_BUNDLE = "/etc/ssl/certs/ca-certificates.crt"


def trusted_ca_bundle() -> str:
    """CA file for verify-full. psycopg's bundled libpq cannot resolve ``sslrootcert=system`` to the image's
    Debian trust store (certificate verify failed in Azure), so the bundle is named explicitly."""
    if os.path.isfile(SYSTEM_CA_BUNDLE):
        return SYSTEM_CA_BUNDLE
    try:
        import certifi
    except ImportError as error:
        raise ValueError("A CA bundle is required to verify Azure PostgreSQL") from error
    return certifi.where()


def build_postgresql_engine(settings: Settings) -> Engine:
    if settings.database_url is None:
        raise ValueError("database URL is required")
    url = make_url(settings.database_url.get_secret_value())
    if settings.runtime_environment == "local":
        if url.drivername != "postgresql+psycopg" or url.host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("local PostgreSQL must use psycopg on loopback")
        url = url.set(
            username=settings.database_username,
            password=settings.database_password.get_secret_value() if settings.database_password else None,
        )
    connect_args: dict[str, str | int] = {"connect_timeout": settings.database_connect_timeout_seconds}
    hosted = settings.runtime_environment not in {"local", "test"}
    if hosted:
        if (
            url.drivername != "postgresql+psycopg"
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.postgres\.database\.azure\.com", url.host or "")
            or not url.username or not url.database or url.password is not None
            or url.query
        ):
            raise ValueError("A password-free Azure PostgreSQL URL with no query parameters is required")
        connect_args.update(sslmode="verify-full", sslrootcert=trusted_ca_bundle(), gssencmode="disable")

    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=settings.database_pool_timeout_seconds,
        connect_args=connect_args,
    )
    if hosted:
        # A user-assigned identity must be named: ManagedIdentityCredential does not read AZURE_CLIENT_ID by itself.
        credential = ManagedIdentityCredential(client_id=os.environ.get("AZURE_CLIENT_ID") or None)

        @event.listens_for(engine, "do_connect")
        def supply_postgresql_token(_dialect, _record, _args, parameters):
            parameters["password"] = credential.get_token(
                "https://ossrdbms-aad.database.windows.net/.default"
            ).token

    return engine


def build_retrieval_service(settings: Settings) -> RetrieveAuthorizedKnowledge:
    embeddings = build_embedding_provider(settings)
    if settings.storage_backend == "memory":
        return RetrieveAuthorizedKnowledge(InMemoryKnowledgeRepository(), embeddings)
    engine = build_postgresql_engine(settings)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    repository = PostgreSQLKnowledgeRepository(
        sessions,
        statement_timeout_ms=settings.database_statement_timeout_ms,
        hnsw_ef_search=settings.hnsw_ef_search,
    )
    return RetrieveAuthorizedKnowledge(repository, embeddings)

