from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import sessionmaker

from .configuration import Settings
from .bootstrap import build_embedding_provider, build_postgresql_engine
from .corpus import CorpusImport, ImportAuthorizedCorpus
from .domain import AuthorizationScope, CorpusKind
from .persistence import PostgreSQLCorpusStore


class ImportFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    source_version: str
    title: str
    provenance: str
    authorization_reference: str
    corpus_kind: CorpusKind
    tenant_id: UUID
    github_installation_id: str
    github_repository_id: str
    pipeline_id: UUID | None = None
    scope_revision: str
    chunks: list[str] = Field(min_length=1)
    correlation_id: str
    reviewed_incident_id: UUID | None = None
    evaluation_material: bool = False


def main() -> None:
    parser = argparse.ArgumentParser(description="Import one pre-authorized sanitized RAG document")
    parser.add_argument("document", type=Path)
    args = parser.parse_args()
    payload = ImportFile.model_validate(json.loads(args.document.read_text(encoding="utf-8")))
    settings = Settings.from_environment()
    if settings.storage_backend != "postgresql" or settings.database_url is None:
        parser.error("PIPESOR_RAG_STORAGE_BACKEND=postgresql and PIPESOR_RAG_DATABASE_URL are required")
    engine = build_postgresql_engine(settings)
    store = PostgreSQLCorpusStore(sessionmaker(bind=engine, expire_on_commit=False))
    importer = ImportAuthorizedCorpus(store, build_embedding_provider(settings))
    request = CorpusImport(
        source_id=payload.source_id,
        source_version=payload.source_version,
        title=payload.title,
        provenance=payload.provenance,
        authorization_reference=payload.authorization_reference,
        corpus_kind=payload.corpus_kind,
        scope=AuthorizationScope(
            payload.tenant_id,
            payload.github_installation_id,
            payload.github_repository_id,
            payload.pipeline_id,
            payload.scope_revision,
        ),
        chunks=tuple(payload.chunks),
        correlation_id=payload.correlation_id,
        reviewed_incident_id=payload.reviewed_incident_id,
        evaluation_material=payload.evaluation_material,
    )
    print(json.dumps({"status": importer.execute(request).value}))


if __name__ == "__main__":
    main()
