"""Fix the approved embedding dimension and index active knowledge vectors."""

from collections.abc import Sequence

from alembic import op
from pgvector.sqlalchemy import VECTOR
import sqlalchemy as sa

revision: str = "20261116_03"
down_revision: str | None = "20261116_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM knowledge.knowledge_chunks) THEN
                RAISE EXCEPTION
                    'knowledge chunks must be re-imported for the approved 1536-dimension embedding contract';
            END IF;
        END $$
        """
    )
    op.alter_column(
        "knowledge_chunks",
        "embedding",
        type_=VECTOR(1536),
        postgresql_using="embedding::vector(1536)",
        schema="knowledge",
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding_model", sa.String(128), nullable=False),
        schema="knowledge",
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding_model_version", sa.String(128), nullable=False),
        schema="knowledge",
    )
    op.create_index(
        "knowledge_chunks_embedding_hnsw_ix",
        "knowledge_chunks",
        ["embedding"],
        unique=False,
        schema="knowledge",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_where=sa.text("embedding IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "knowledge_chunks_embedding_hnsw_ix",
        table_name="knowledge_chunks",
        schema="knowledge",
    )
    op.drop_column("knowledge_chunks", "embedding_model_version", schema="knowledge")
    op.drop_column("knowledge_chunks", "embedding_model", schema="knowledge")
    op.alter_column(
        "knowledge_chunks",
        "embedding",
        type_=VECTOR(),
        postgresql_using="embedding::vector",
        schema="knowledge",
    )
