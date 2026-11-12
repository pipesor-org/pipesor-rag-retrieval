from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .application import RetrievalQuery, RetrieveAuthorizedKnowledge
from .bootstrap import build_retrieval_service
from .configuration import Settings
from .domain import AuthorizationScope, CorpusKind

SafeId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")]
PositiveExternalId = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]*$", max_length=32)]


class ScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID
    installation_id: PositiveExternalId
    repository_id: PositiveExternalId
    pipeline_id: UUID | None = None
    revision: SafeId


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal["1.0"]
    correlation_id: SafeId
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    authorization_scope: ScopeRequest
    allowed_corpus_kinds: list[CorpusKind] = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("allowed_corpus_kinds")
    @classmethod
    def unique_kinds(cls, value: list[CorpusKind]) -> list[CorpusKind]:
        if len(set(value)) != len(value):
            raise ValueError("allowed_corpus_kinds must be unique")
        return value


class MatchResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    corpus_kind: CorpusKind
    title: str
    content: str
    provenance: str
    score: float


class RetrievalResponse(BaseModel):
    contract_version: Literal["1.0"] = "1.0"
    correlation_id: str
    status: Literal["matches", "no_match"]
    matches: list[MatchResponse]


class InternalCaller:
    def __init__(self, expected: str) -> None:
        self.expected = expected

    def __call__(self, x_pipesor_caller: Annotated[str | None, Header()] = None) -> str:
        if x_pipesor_caller != self.expected:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="caller_not_authorized")
        return x_pipesor_caller


def create_app(
    service: RetrieveAuthorizedKnowledge | None = None,
    authenticate: Callable[..., str] | None = None,
) -> FastAPI:
    retrieval = service or build_retrieval_service(Settings.from_environment())
    caller = authenticate or InternalCaller("recommendation_service")
    app = FastAPI(title="Pipesor RAG Retrieval", version="1.0.0", docs_url=None, redoc_url=None)

    @app.get("/health/live", include_in_schema=False)
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready", include_in_schema=False)
    def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.post("/internal/v1/retrieval/query", response_model=RetrievalResponse)
    def retrieve(request: RetrievalRequest, _: str = Depends(caller)) -> RetrievalResponse:
        scope = AuthorizationScope(**request.authorization_scope.model_dump())
        try:
            result = retrieval.execute(
                RetrievalQuery(
                    correlation_id=request.correlation_id,
                    query=request.query,
                    scope=scope,
                    allowed_corpus_kinds=frozenset(request.allowed_corpus_kinds),
                    top_k=request.top_k,
                )
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        matches = [
            MatchResponse(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                corpus_kind=item.corpus_kind,
                title=item.title,
                content=item.content,
                provenance=item.provenance,
                score=item.score,
            )
            for item in result
        ]
        return RetrievalResponse(
            correlation_id=request.correlation_id,
            status="matches" if matches else "no_match",
            matches=matches,
        )

    return app


app = create_app()

