from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select, text, update
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .domain import AuthorizationScope, CorpusKind, KnowledgeChunk
from .corpus import ImportStatus, PreparedDocument


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
    github_installation_id: Mapped[str] = mapped_column(String(32), nullable=False)
    github_repository_id: Mapped[str] = mapped_column(String(32), nullable=False)
    pipeline_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    scope_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    source_id: Mapped[str] = mapped_column(String(256), nullable=False)
    source_version: Mapped[str] = mapped_column(String(128), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    authorization_reference: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
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
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR(1536), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PostgreSQLKnowledgeRepository:
    """Bounded, scope-first adapter used until a dimensioned vector index is approved."""

    def __init__(self, session_factory: Callable[[], Session], candidate_limit: int = 1000) -> None:
        if candidate_limit < 1:
            raise ValueError("candidate_limit must be positive")
        self._session_factory = session_factory
        self._candidate_limit = candidate_limit

    def candidates(
        self,
        scope: AuthorizationScope,
        query_embedding: tuple[float, ...],
        embedding_model: str,
        embedding_model_version: str,
    ) -> tuple[KnowledgeChunk, ...]:
        if len(query_embedding) != 1536:
            raise ValueError("query embedding must contain 1536 dimensions")
        statement = (
            select(KnowledgeChunkRecord, KnowledgeDocumentRecord)
            .join(KnowledgeDocumentRecord, KnowledgeDocumentRecord.id == KnowledgeChunkRecord.document_id)
            .where(
                KnowledgeDocumentRecord.tenant_id == scope.tenant_id,
                KnowledgeDocumentRecord.github_installation_id == scope.github_installation_id,
                KnowledgeDocumentRecord.github_repository_id == scope.github_repository_id,
                KnowledgeDocumentRecord.scope_revision == scope.scope_revision,
                KnowledgeDocumentRecord.active.is_(True),
                KnowledgeChunkRecord.embedding.is_not(None),
                KnowledgeChunkRecord.embedding_model == embedding_model,
                KnowledgeChunkRecord.embedding_model_version == embedding_model_version,
            )
            .order_by(
                KnowledgeChunkRecord.embedding.cosine_distance(list(query_embedding)),
                KnowledgeChunkRecord.id,
            )
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

    def ready(self) -> bool:
        with self._session_factory() as session:
            return session.scalar(select(1)) == 1

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
                github_installation_id=document.github_installation_id,
                github_repository_id=document.github_repository_id,
                pipeline_id=document.pipeline_id,
                scope_revision=document.scope_revision,
            ),
            embedding=tuple(float(value) for value in chunk.embedding),
        )


class PostgreSQLCorpusStore:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def import_document(self, document: PreparedDocument) -> ImportStatus:
        request = document.request
        scope = request.scope
        with self._session_factory() as session:
            existing = session.scalar(
                select(KnowledgeDocumentRecord).where(
                    KnowledgeDocumentRecord.tenant_id == scope.tenant_id,
                    KnowledgeDocumentRecord.github_repository_id == scope.github_repository_id,
                    KnowledgeDocumentRecord.source_id == request.source_id,
                    KnowledgeDocumentRecord.source_version == request.source_version,
                )
            )
            if existing is not None:
                if existing.content_hash != document.content_hash:
                    raise ValueError("source version already exists with different content")
                return ImportStatus.UNCHANGED
            replaced = session.scalar(
                select(KnowledgeDocumentRecord.id).where(
                    KnowledgeDocumentRecord.tenant_id == scope.tenant_id,
                    KnowledgeDocumentRecord.github_repository_id == scope.github_repository_id,
                    KnowledgeDocumentRecord.source_id == request.source_id,
                    KnowledgeDocumentRecord.active.is_(True),
                ).limit(1)
            ) is not None
            session.execute(
                update(KnowledgeDocumentRecord)
                .where(
                    KnowledgeDocumentRecord.tenant_id == scope.tenant_id,
                    KnowledgeDocumentRecord.github_repository_id == scope.github_repository_id,
                    KnowledgeDocumentRecord.source_id == request.source_id,
                    KnowledgeDocumentRecord.active.is_(True),
                )
                .values(active=False)
            )
            record = KnowledgeDocumentRecord(
                id=document.id,
                corpus_kind=request.corpus_kind.value,
                title=request.title,
                provenance=request.provenance,
                reviewed_incident_id=request.reviewed_incident_id,
                tenant_id=scope.tenant_id,
                github_installation_id=scope.github_installation_id,
                github_repository_id=scope.github_repository_id,
                pipeline_id=scope.pipeline_id,
                scope_revision=scope.scope_revision,
                source_id=request.source_id,
                source_version=request.source_version,
                content_hash=document.content_hash,
                authorization_reference=request.authorization_reference,
                active=True,
                correlation_id=request.correlation_id,
                created_at=datetime.now(UTC),
            )
            session.add(record)
            # The records intentionally expose only identifiers rather than an ORM
            # relationship. Flush the parent explicitly so PostgreSQL can enforce
            # the chunk foreign key regardless of SQLAlchemy's unit-of-work order.
            session.flush()
            session.add_all(
                KnowledgeChunkRecord(
                    id=chunk.id,
                    document_id=document.id,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    provenance=chunk.provenance,
                    embedding=list(chunk.embedding),
                    embedding_model=chunk.embedding_model,
                    embedding_model_version=chunk.embedding_model_version,
                    correlation_id=request.correlation_id,
                    created_at=record.created_at,
                )
                for chunk in document.chunks
            )
            session.commit()
            return ImportStatus.REPLACED if replaced else ImportStatus.CREATED

