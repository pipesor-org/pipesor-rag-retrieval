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

    @model_validator(mode="after")
    def require_database_url(self) -> Settings:
        if self.storage_backend == "postgresql" and self.database_url is None:
            raise ValueError("PIPESOR_RAG_DATABASE_URL is required for PostgreSQL storage")
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
        }
        for field, environment_name in mapping.items():
            if value := os.environ.get(environment_name):
                values[field] = value
        return cls.model_validate(values)

