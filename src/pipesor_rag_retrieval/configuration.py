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

    @model_validator(mode="after")
    def require_database_url(self) -> Settings:
        if self.storage_backend == "postgresql" and self.database_url is None:
            raise ValueError("PIPESOR_RAG_DATABASE_URL is required for PostgreSQL storage")
        if self.runtime_environment not in {"local", "test"} and self.authentication_mode == "simulated":
            raise ValueError("simulated authentication is forbidden outside local/test")
        if self.authentication_mode == "entra":
            raise ValueError("Entra authentication is not implemented")
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
        }
        for field, environment_name in mapping.items():
            if value := os.environ.get(environment_name):
                values[field] = value
        return cls.model_validate(values)

