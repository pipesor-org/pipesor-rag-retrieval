from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .domain import AuthorizationScope, CorpusKind, KnowledgeChunk


class Base(DeclarativeBase):
    pass


class KnowledgeDocumentRecord(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint("btrim(provenance) <> ''", name="knowledge_documents_provenance_ck"),
        CheckConstraint(
            "corpus_kind <> 'reviewed_incidents' OR reviewed_incident_id IS NOT NULL",
            name="knowledge_documents_reviewed_incident_ck",
        ),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    corpus_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_incident_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    tenant_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    installation_id: Mapped[str] = mapped_column(String(32), nullable=False)
    repository_id: Mapped[str] = mapped_column(String(32), nullable=False)
    pipeline_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    authorization_scope_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KnowledgeChunkRecord(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="knowledge_chunks_document_index_uq"),
        CheckConstraint("chunk_index >= 0", name="knowledge_chunks_index_ck"),
        CheckConstraint("btrim(provenance) <> ''", name="knowledge_chunks_provenance_ck"),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("knowledge.knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR(), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PostgreSQLKnowledgeRepository:
    """Bounded, scope-first adapter used until a dimensioned vector index is approved."""

    def __init__(self, session_factory: Callable[[], Session], candidate_limit: int = 1000) -> None:
        if candidate_limit < 1:
            raise ValueError("candidate_limit must be positive")
        self._session_factory = session_factory
        self._candidate_limit = candidate_limit

    def candidates(self, scope: AuthorizationScope) -> tuple[KnowledgeChunk, ...]:
        statement = (
            select(KnowledgeChunkRecord, KnowledgeDocumentRecord)
            .join(KnowledgeDocumentRecord, KnowledgeDocumentRecord.id == KnowledgeChunkRecord.document_id)
            .where(
                KnowledgeDocumentRecord.tenant_id == scope.tenant_id,
                KnowledgeDocumentRecord.installation_id == scope.installation_id,
                KnowledgeDocumentRecord.repository_id == scope.repository_id,
                KnowledgeDocumentRecord.authorization_scope_revision == scope.revision,
                KnowledgeChunkRecord.embedding.is_not(None),
            )
            .order_by(KnowledgeChunkRecord.id)
            .limit(self._candidate_limit)
        )
        statement = statement.where(
            KnowledgeDocumentRecord.pipeline_id.is_(None)
            if scope.pipeline_id is None
            else KnowledgeDocumentRecord.pipeline_id == scope.pipeline_id
        )
        with self._session_factory() as session:
            rows = session.execute(statement).all()
        return tuple(self._to_domain(chunk, document) for chunk, document in rows)

    @staticmethod
    def _to_domain(
        chunk: KnowledgeChunkRecord, document: KnowledgeDocumentRecord
    ) -> KnowledgeChunk:
        if chunk.embedding is None:
            raise ValueError("stored chunk is missing its embedding")
        return KnowledgeChunk(
            id=chunk.id,
            document_id=document.id,
            chunk_index=chunk.chunk_index,
            corpus_kind=CorpusKind(document.corpus_kind),
            title=document.title,
            content=chunk.content,
            provenance=chunk.provenance,
            scope=AuthorizationScope(
                tenant_id=document.tenant_id,
                installation_id=document.installation_id,
                repository_id=document.repository_id,
                pipeline_id=document.pipeline_id,
                revision=document.authorization_scope_revision,
            ),
            embedding=tuple(float(value) for value in chunk.embedding),
        )

