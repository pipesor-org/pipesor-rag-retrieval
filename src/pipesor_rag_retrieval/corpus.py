from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from .domain import AuthorizationScope, CorpusKind
from .ports import EmbeddingProvider


@dataclass(frozen=True, slots=True)
class CorpusImport:
    source_id: str
    source_version: str
    title: str
    provenance: str
    authorization_reference: str
    corpus_kind: CorpusKind
    scope: AuthorizationScope
    chunks: tuple[str, ...]
    correlation_id: str
    reviewed_incident_id: UUID | None = None
    evaluation_material: bool = False


@dataclass(frozen=True, slots=True)
class PreparedChunk:
    id: UUID
    index: int
    content: str
    provenance: str
    embedding: tuple[float, ...]
    embedding_model: str
    embedding_model_version: str


@dataclass(frozen=True, slots=True)
class PreparedDocument:
    id: UUID
    request: CorpusImport
    content_hash: str
    chunks: tuple[PreparedChunk, ...]


class ImportStatus(StrEnum):
    CREATED = "created"
    UNCHANGED = "unchanged"
    REPLACED = "replaced"


class CorpusStore(Protocol):
    def import_document(self, document: PreparedDocument) -> ImportStatus: ...


class ImportAuthorizedCorpus:
    def __init__(self, store: CorpusStore, embeddings: EmbeddingProvider) -> None:
        self._store = store
        self._embeddings = embeddings

    def execute(self, request: CorpusImport) -> ImportStatus:
        for name, value in (
            ("source_id", request.source_id),
            ("source_version", request.source_version),
            ("title", request.title),
            ("provenance", request.provenance),
            ("authorization_reference", request.authorization_reference),
            ("correlation_id", request.correlation_id),
        ):
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if request.evaluation_material:
            raise ValueError("evaluation material cannot enter the retrieval corpus")
        if request.corpus_kind is CorpusKind.REVIEWED_INCIDENTS and request.reviewed_incident_id is None:
            raise ValueError("reviewed_incident_id is required for reviewed incidents")
        if not request.chunks or any(not chunk.strip() for chunk in request.chunks):
            raise ValueError("chunks must contain non-empty sanitized content")
        canonical = json.dumps(
            {
                "source_id": request.source_id,
                "source_version": request.source_version,
                "title": request.title,
                "provenance": request.provenance,
                "corpus_kind": request.corpus_kind.value,
                "scope": {
                    "tenant_id": str(request.scope.tenant_id),
                    "github_installation_id": request.scope.github_installation_id,
                    "github_repository_id": request.scope.github_repository_id,
                    "pipeline_id": str(request.scope.pipeline_id) if request.scope.pipeline_id else None,
                    "scope_revision": request.scope.scope_revision,
                },
                "chunks": request.chunks,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        content_hash = hashlib.sha256(canonical).hexdigest()
        identity = f"urn:pipesor:v1:knowledge:{request.scope.tenant_id}:{request.source_id}:{request.source_version}"
        document_id = uuid5(NAMESPACE_URL, identity)
        chunks = tuple(
            PreparedChunk(
                id=uuid5(NAMESPACE_URL, f"{identity}:chunk:{index}"),
                index=index,
                content=content.strip(),
                provenance=f"{request.provenance}#chunk={index}",
                embedding=self._embeddings.embed(content),
                embedding_model=self._embeddings.model_name,
                embedding_model_version=self._embeddings.model_version,
            )
            for index, content in enumerate(request.chunks)
        )
        return self._store.import_document(PreparedDocument(document_id, request, content_hash, chunks))


class InMemoryCorpusStore:
    def __init__(self) -> None:
        self.documents: dict[tuple[UUID, str, str, str], PreparedDocument] = {}

    def import_document(self, document: PreparedDocument) -> ImportStatus:
        request = document.request
        key = (request.scope.tenant_id, request.scope.github_repository_id, request.source_id, request.source_version)
        existing = self.documents.get(key)
        if existing:
            if existing.content_hash != document.content_hash:
                raise ValueError("source version already exists with different content")
            return ImportStatus.UNCHANGED
        replaced = any(
            stored.request.scope.tenant_id == request.scope.tenant_id
            and stored.request.scope.github_repository_id == request.scope.github_repository_id
            and stored.request.source_id == request.source_id
            for stored in self.documents.values()
        )
        self.documents[key] = document
        return ImportStatus.REPLACED if replaced else ImportStatus.CREATED

