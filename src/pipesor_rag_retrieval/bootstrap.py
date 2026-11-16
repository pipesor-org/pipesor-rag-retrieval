from __future__ import annotations

from sqlalchemy import create_engine
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


def build_retrieval_service(settings: Settings) -> RetrieveAuthorizedKnowledge:
    embeddings = build_embedding_provider(settings)
    if settings.storage_backend == "memory":
        return RetrieveAuthorizedKnowledge(InMemoryKnowledgeRepository(), embeddings)
    if settings.database_url is None:
        raise ValueError("database URL is required")
    engine = create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=settings.database_pool_timeout_seconds,
        connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
    )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    repository = PostgreSQLKnowledgeRepository(sessions, settings.candidate_limit)
    return RetrieveAuthorizedKnowledge(repository, embeddings)

