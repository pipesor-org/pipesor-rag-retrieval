"""Adopt canonical GitHub scope names and corpus lifecycle metadata."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261116_02"
down_revision: str | None = "20261111_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("knowledge_documents_scope_ix", table_name="knowledge_documents", schema="knowledge")
    op.alter_column("knowledge_documents", "installation_id", new_column_name="github_installation_id", schema="knowledge")
    op.alter_column("knowledge_documents", "repository_id", new_column_name="github_repository_id", schema="knowledge")
    op.alter_column("knowledge_documents", "authorization_scope_revision", new_column_name="scope_revision", schema="knowledge")
    for name, type_ in (
        ("source_id", sa.String(256)),
        ("source_version", sa.String(128)),
        ("content_hash", sa.String(64)),
        ("authorization_reference", sa.Text()),
    ):
        op.add_column("knowledge_documents", sa.Column(name, type_, nullable=True), schema="knowledge")
    op.add_column("knowledge_documents", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), schema="knowledge")
    op.execute("""
        UPDATE knowledge.knowledge_documents
        SET source_id = 'legacy:' || id::text,
            source_version = 'legacy',
            content_hash = repeat('0', 64),
            authorization_reference = provenance
    """)
    for name in ("source_id", "source_version", "content_hash", "authorization_reference"):
        op.alter_column("knowledge_documents", name, nullable=False, schema="knowledge")
    op.create_unique_constraint(
        "knowledge_documents_source_version_uq",
        "knowledge_documents",
        ["tenant_id", "github_repository_id", "source_id", "source_version"],
        schema="knowledge",
    )
    op.create_check_constraint("knowledge_documents_content_hash_ck", "knowledge_documents", "content_hash ~ '^[0-9a-f]{64}$'", schema="knowledge")
    op.create_check_constraint("knowledge_documents_authorization_ck", "knowledge_documents", "btrim(authorization_reference) <> ''", schema="knowledge")
    op.create_index(
        "knowledge_documents_scope_ix",
        "knowledge_documents",
        ["tenant_id", "github_installation_id", "github_repository_id", "pipeline_id", "scope_revision", "active"],
        schema="knowledge",
    )


def downgrade() -> None:
    op.drop_index("knowledge_documents_scope_ix", table_name="knowledge_documents", schema="knowledge")
    op.drop_constraint("knowledge_documents_authorization_ck", "knowledge_documents", schema="knowledge", type_="check")
    op.drop_constraint("knowledge_documents_content_hash_ck", "knowledge_documents", schema="knowledge", type_="check")
    op.drop_constraint("knowledge_documents_source_version_uq", "knowledge_documents", schema="knowledge", type_="unique")
    for name in ("active", "authorization_reference", "content_hash", "source_version", "source_id"):
        op.drop_column("knowledge_documents", name, schema="knowledge")
    op.alter_column("knowledge_documents", "scope_revision", new_column_name="authorization_scope_revision", schema="knowledge")
    op.alter_column("knowledge_documents", "github_repository_id", new_column_name="repository_id", schema="knowledge")
    op.alter_column("knowledge_documents", "github_installation_id", new_column_name="installation_id", schema="knowledge")
    op.create_index("knowledge_documents_scope_ix", "knowledge_documents", ["tenant_id", "installation_id", "repository_id", "pipeline_id", "authorization_scope_revision"], schema="knowledge")
