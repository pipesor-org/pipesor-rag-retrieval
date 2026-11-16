from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str = "0.0.0.0"
    port: int = Field(default=8080, ge=1, le=65535)
    storage_backend: Literal["memory", "postgresql"] = "memory"
    database_url: SecretStr | None = None
    candidate_limit: int = Field(default=1000, ge=1, le=10000)
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    database_pool_timeout_seconds: int = Field(default=5, ge=1, le=30)
    max_request_bytes: int = Field(default=65536, ge=1024, le=1048576)
    runtime_environment: Literal["local", "test", "dev", "qa", "prod"] = "local"
    authentication_mode: Literal["simulated", "entra"] = "simulated"
    embedding_backend: Literal["deterministic", "azure_openai"] = "deterministic"
    embedding_model: Literal["text-embedding-3-small"] = "text-embedding-3-small"
    embedding_model_version: str = Field(default="simulated-v1", min_length=1, max_length=128)
    embedding_dimension: Literal[1536] = 1536
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None
    embedding_timeout_seconds: int = Field(default=15, ge=1, le=60)
    embedding_max_retries: int = Field(default=2, ge=0, le=2)

    @model_validator(mode="after")
    def require_database_url(self) -> Settings:
        if self.storage_backend == "postgresql" and self.database_url is None:
            raise ValueError("PIPESOR_RAG_DATABASE_URL is required for PostgreSQL storage")
        if self.runtime_environment not in {"local", "test"} and self.authentication_mode == "simulated":
            raise ValueError("simulated authentication is forbidden outside local/test")
        if self.authentication_mode == "entra":
            raise ValueError("Entra authentication is not implemented")
        if self.embedding_backend == "azure_openai":
            if not self.azure_openai_endpoint or not self.azure_openai_deployment:
                raise ValueError("Azure OpenAI endpoint and deployment are required")
            if not self.azure_openai_endpoint.startswith("https://"):
                raise ValueError("Azure OpenAI endpoint must use HTTPS")
        return self

    @classmethod
    def from_environment(cls) -> Settings:
        values: dict[str, object] = {}
        mapping = {
            "host": "PIPESOR_RAG_HOST",
            "port": "PIPESOR_RAG_PORT",
            "storage_backend": "PIPESOR_RAG_STORAGE_BACKEND",
            "database_url": "PIPESOR_RAG_DATABASE_URL",
            "candidate_limit": "PIPESOR_RAG_CANDIDATE_LIMIT",
            "database_connect_timeout_seconds": "PIPESOR_RAG_DATABASE_CONNECT_TIMEOUT_SECONDS",
            "database_pool_timeout_seconds": "PIPESOR_RAG_DATABASE_POOL_TIMEOUT_SECONDS",
            "max_request_bytes": "PIPESOR_RAG_MAX_REQUEST_BYTES",
            "runtime_environment": "PIPESOR_RAG_ENVIRONMENT",
            "authentication_mode": "PIPESOR_RAG_AUTHENTICATION_MODE",
            "embedding_backend": "PIPESOR_RAG_EMBEDDING_BACKEND",
            "embedding_model": "PIPESOR_RAG_EMBEDDING_MODEL",
            "embedding_model_version": "PIPESOR_RAG_EMBEDDING_MODEL_VERSION",
            "embedding_dimension": "PIPESOR_RAG_EMBEDDING_DIMENSION",
            "azure_openai_endpoint": "PIPESOR_RAG_AZURE_OPENAI_ENDPOINT",
            "azure_openai_deployment": "PIPESOR_RAG_AZURE_OPENAI_DEPLOYMENT",
            "embedding_timeout_seconds": "PIPESOR_RAG_EMBEDDING_TIMEOUT_SECONDS",
            "embedding_max_retries": "PIPESOR_RAG_EMBEDDING_MAX_RETRIES",
        }
        for field, environment_name in mapping.items():
            if value := os.environ.get(environment_name):
                values[field] = value
        return cls.model_validate(values)

