from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import sqrt
from uuid import UUID


class CorpusKind(StrEnum):
    REVIEWED_INCIDENTS = "reviewed_incidents"
    AUTHORIZED_TECHNICAL_DOCUMENTATION = "authorized_technical_documentation"
    AUTHORIZED_RESPONSE_PROCEDURES = "authorized_response_procedures"


@dataclass(frozen=True, slots=True)
class AuthorizationScope:
    tenant_id: UUID
    installation_id: str
    repository_id: str
    pipeline_id: UUID | None = None
    revision: str = ""

    def permits(self, candidate: AuthorizationScope) -> bool:
        return (
            self.tenant_id == candidate.tenant_id
            and self.installation_id == candidate.installation_id
            and self.repository_id == candidate.repository_id
            and (candidate.pipeline_id is None or self.pipeline_id == candidate.pipeline_id)
            and self.revision == candidate.revision
        )


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    id: UUID
    document_id: UUID
    chunk_index: int
    corpus_kind: CorpusKind
    title: str
    content: str
    provenance: str
    scope: AuthorizationScope
    embedding: tuple[float, ...]
    evaluation_material: bool = False

    def __post_init__(self) -> None:
        if self.chunk_index < 0:
            raise ValueError("chunk_index must be non-negative")
        if not self.content.strip() or not self.provenance.strip():
            raise ValueError("content and provenance must be non-empty")
        if self.evaluation_material:
            raise ValueError("evaluation material cannot enter the retrieval corpus")


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or len(left) != len(right):
        raise ValueError("incompatible embedding vectors")
    denominator = sqrt(sum(value * value for value in left)) * sqrt(
        sum(value * value for value in right)
    )
    if denominator == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / denominator

