"""Create the authorized knowledge foundation without a vector index."""

from collections.abc import Sequence

from alembic import op
from pgvector.sqlalchemy import VECTOR
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20261111_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS knowledge")
    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("corpus_kind", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=False),
        sa.Column("reviewed_incident_id", postgresql.UUID(as_uuid=True)),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("installation_id", sa.String(32), nullable=False),
        sa.Column("repository_id", sa.String(32), nullable=False),
        sa.Column("pipeline_id", postgresql.UUID(as_uuid=True)),
        sa.Column("authorization_scope_revision", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("btrim(provenance) <> ''", name="knowledge_documents_provenance_ck"),
        sa.CheckConstraint(
            "corpus_kind IN ('reviewed_incidents','authorized_technical_documentation','authorized_response_procedures')",
            name="knowledge_documents_corpus_kind_ck",
        ),
        sa.CheckConstraint(
            "corpus_kind <> 'reviewed_incidents' OR reviewed_incident_id IS NOT NULL",
            name="knowledge_documents_reviewed_incident_ck",
        ),
        schema="knowledge",
    )
    op.create_index(
        "knowledge_documents_scope_ix",
        "knowledge_documents",
        ["tenant_id", "installation_id", "repository_id", "pipeline_id", "authorization_scope_revision"],
        schema="knowledge",
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge.knowledge_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=False),
        sa.Column("embedding", VECTOR(), nullable=True),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_id", "chunk_index", name="knowledge_chunks_document_index_uq"),
        sa.CheckConstraint("chunk_index >= 0", name="knowledge_chunks_index_ck"),
        sa.CheckConstraint("btrim(content) <> ''", name="knowledge_chunks_content_ck"),
        sa.CheckConstraint("btrim(provenance) <> ''", name="knowledge_chunks_provenance_ck"),
        schema="knowledge",
    )


def downgrade() -> None:
    op.drop_table("knowledge_chunks", schema="knowledge")
    op.drop_index("knowledge_documents_scope_ix", table_name="knowledge_documents", schema="knowledge")
    op.drop_table("knowledge_documents", schema="knowledge")

