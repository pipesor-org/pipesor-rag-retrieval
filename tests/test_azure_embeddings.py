from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest
from openai import RateLimitError

from pipesor_rag_retrieval.infrastructure import AzureOpenAIEmbeddingProvider


@dataclass
class EmbeddingData:
    embedding: list[float]


@dataclass
class EmbeddingResponse:
    data: list[EmbeddingData]


class FakeEmbeddings:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def response(dimension: int = 1536) -> EmbeddingResponse:
    return EmbeddingResponse([EmbeddingData([0.25] * dimension)])


def rate_limit_error() -> RateLimitError:
    request = httpx.Request("POST", "https://foundry.invalid/openai/v1/embeddings")
    raw = httpx.Response(429, request=request, headers={"retry-after": "1"})
    return RateLimitError("synthetic throttle", response=raw, body=None)


def test_azure_provider_uses_approved_deployment_and_dimension() -> None:
    endpoint = FakeEmbeddings([response()])
    provider = AzureOpenAIEmbeddingProvider(
        "https://foundry.invalid",
        "pipesor-dev-embeddings",
        "2026-11",
        embeddings=endpoint,
    )

    vector = provider.embed("synthetic sanitized input")

    assert len(vector) == 1536
    assert endpoint.calls[0]["model"] == "pipesor-dev-embeddings"
    assert endpoint.calls[0]["dimensions"] == 1536


def test_azure_provider_retries_transient_failure_within_total_budget() -> None:
    now = [0.0]
    endpoint = FakeEmbeddings([rate_limit_error(), response()])
    provider = AzureOpenAIEmbeddingProvider(
        "https://foundry.invalid",
        "pipesor-dev-embeddings",
        "2026-11",
        timeout_seconds=15,
        max_retries=2,
        embeddings=endpoint,
        clock=lambda: now[0],
        sleep=lambda delay: now.__setitem__(0, now[0] + delay),
    )

    assert len(provider.embed("synthetic sanitized input")) == 1536
    assert len(endpoint.calls) == 2
    assert endpoint.calls[1]["timeout"] == 14.0


def test_azure_provider_rejects_incompatible_vector() -> None:
    provider = AzureOpenAIEmbeddingProvider(
        "https://foundry.invalid",
        "pipesor-dev-embeddings",
        "2026-11",
        embeddings=FakeEmbeddings([response(8)]),
    )

    with pytest.raises(ValueError, match="incompatible vector"):
        provider.embed("synthetic sanitized input")
