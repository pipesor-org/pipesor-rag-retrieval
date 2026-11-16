from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .application import RetrieveAuthorizedKnowledge
from .configuration import Settings
from .infrastructure import DeterministicEmbeddingProvider, InMemoryKnowledgeRepository
from .persistence import PostgreSQLKnowledgeRepository


def build_retrieval_service(settings: Settings) -> RetrieveAuthorizedKnowledge:
    embeddings = DeterministicEmbeddingProvider()
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

