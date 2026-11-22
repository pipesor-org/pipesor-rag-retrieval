from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from typing import Protocol

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError

from .domain import AuthorizationScope, KnowledgeChunk
from .domain import CorpusKind, cosine_similarity
from .ports import RankedKnowledgeChunk


class DeterministicEmbeddingProvider:
    """Test/local adapter only; it is not a semantic production embedding model."""

    model_name = "text-embedding-3-small"
    model_version = "simulated-v1"
    dimension = 1536

    def embed(self, text: str) -> tuple[float, ...]:
        if not text.strip():
            raise ValueError("query must be non-empty")
        seed = hashlib.sha256(text.casefold().encode("utf-8")).digest()
        material = bytearray()
        counter = 0
        while len(material) < self.dimension:
            material.extend(hashlib.sha256(seed + counter.to_bytes(4, "big")).digest())
            counter += 1
        return tuple((value - 127.5) / 127.5 for value in material[: self.dimension])


class EmbeddingsEndpoint(Protocol):
    def create(self, **kwargs: object) -> object: ...


class AzureOpenAIEmbeddingProvider:
    """Azure OpenAI v1 adapter with one bounded retry layer."""

    model_name = "text-embedding-3-small"
    dimension = 1536

    def __init__(
        self,
        endpoint: str,
        deployment: str,
        model_version: str,
        timeout_seconds: int = 15,
        max_retries: int = 2,
        *,
        embeddings: EmbeddingsEndpoint | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.deployment = deployment
        self.model_version = model_version
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._clock = clock
        self._sleep = sleep
        if embeddings is None:
            credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(credential, "https://ai.azure.com/.default")
            client = OpenAI(
                base_url=f"{endpoint.rstrip('/')}/openai/v1/",
                api_key=token_provider,
                max_retries=0,
                timeout=timeout_seconds,
            )
            embeddings = client.embeddings
        self._embeddings = embeddings

    def embed(self, text: str) -> tuple[float, ...]:
        if not text.strip():
            raise ValueError("query must be non-empty")
        deadline = self._clock() + self.timeout_seconds
        for attempt in range(self.max_retries + 1):
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise TimeoutError("embedding time budget exhausted")
            try:
                response = self._embeddings.create(
                    model=self.deployment,
                    input=text,
                    dimensions=self.dimension,
                    timeout=remaining,
                )
                vector = tuple(float(value) for value in response.data[0].embedding)  # type: ignore[attr-defined]
                if len(vector) != self.dimension:
                    raise ValueError("embedding provider returned an incompatible vector")
                return vector
            except (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError) as error:
                if attempt >= self.max_retries:
                    raise
                retry_after = getattr(getattr(error, "response", None), "headers", {}).get(
                    "retry-after"
                )
                try:
                    requested_delay = float(retry_after) if retry_after is not None else 2**attempt
                except ValueError:
                    requested_delay = 2**attempt
                delay = min(max(0.0, requested_delay), max(0.0, deadline - self._clock()))
                if delay <= 0:
                    raise TimeoutError("embedding time budget exhausted")
                self._sleep(delay)
        raise RuntimeError("unreachable")


class InMemoryKnowledgeRepository:
    def __init__(self, chunks: tuple[KnowledgeChunk, ...] = ()) -> None:
        self._chunks = chunks

    def search(
        self,
        scope: AuthorizationScope,
        query_embedding: tuple[float, ...],
        embedding_model: str,
        embedding_model_version: str,
        allowed_corpus_kinds: frozenset[CorpusKind],
        top_k: int,
    ) -> tuple[RankedKnowledgeChunk, ...]:
        matches = [
            RankedKnowledgeChunk(chunk, cosine_similarity(query_embedding, chunk.embedding))
            for chunk in self._chunks
            if scope.permits(chunk.scope) and chunk.corpus_kind in allowed_corpus_kinds
        ]
        return tuple(sorted(matches, key=lambda item: (-item.score, str(item.chunk.id)))[:top_k])

    def ready(self) -> bool:
        return True

