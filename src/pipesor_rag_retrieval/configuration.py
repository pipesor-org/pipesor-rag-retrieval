from __future__ import annotations

import os
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str = "127.0.0.1"
    port: int = Field(default=8087, ge=1, le=65535)
    runtime_environment: Literal["local", "azure", "test"] = "test"
    storage_backend: Literal["memory", "postgresql"] = "memory"
    database_url: SecretStr | None = None
    database_username: str | None = None
    database_password: SecretStr | None = None
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    database_pool_timeout_seconds: int = Field(default=5, ge=1, le=30)
    database_statement_timeout_ms: int = Field(default=5000, ge=100, le=15000)
    hnsw_ef_search: int = Field(default=100, ge=1, le=1000)
    max_request_bytes: int = Field(default=65536, ge=1024, le=1048576)

    authentication_mode: Literal["test", "platform", "entra"] = "test"
    tenant_id: UUID | None = None
    security_audience: str | None = None
    trusted_workload_id: str | None = None
    trusted_jwks_uri: str | None = None
    trusted_roles: str | None = None
    entra_tenant_id: UUID | None = None
    entra_audience: UUID | None = None
    entra_recommendation_client_id: UUID | None = None
    entra_required_role: Literal["Rag.Query"] = "Rag.Query"

    embedding_backend: Literal["deterministic", "azure_openai"] = "deterministic"
    embedding_model: Literal["text-embedding-3-small"] = "text-embedding-3-small"
    embedding_model_version: str = Field(default="simulated-v1", min_length=1, max_length=128)
    embedding_dimension: Literal[1536] = 1536
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None
    embedding_timeout_seconds: int = Field(default=15, ge=1, le=15)
    embedding_max_retries: int = Field(default=2, ge=0, le=2)

    @model_validator(mode="after")
    def secure_runtime(self) -> "Settings":
        if self.runtime_environment != "test":
            expected_bind = ("127.0.0.1", 8087) if self.runtime_environment == "local" else ("0.0.0.0", 8080)
            if (self.host, self.port) != expected_bind:
                raise ValueError("SERVER_ADDRESS and SERVER_PORT must match the runtime manifest")
            if self.storage_backend != "postgresql" or self.embedding_backend != "azure_openai":
                raise ValueError("runtime requires PostgreSQL and Azure OpenAI backends")
            if self.authentication_mode == "test":
                raise ValueError("test authentication is forbidden outside automated tests")
        if self.storage_backend == "postgresql" and self.database_url is None:
            raise ValueError("PIPESOR_DATABASE_URL is required for PostgreSQL storage")
        if self.runtime_environment == "local" and (not self.database_username or self.database_password is None):
            raise ValueError("local PostgreSQL username and password are required")
        if self.runtime_environment == "azure" and (self.database_username or self.database_password):
            raise ValueError("azure PostgreSQL must not use configured passwords")
        if self.authentication_mode == "platform":
            expected = (
                self.tenant_id and self.security_audience == "urn:pipesor:api:rag"
                and self.trusted_workload_id == "recommendation" and self.trusted_jwks_uri
                and self.trusted_roles == "Rag.Query"
            )
            if not expected:
                raise ValueError("platform authentication settings do not match the approved caller")
            _transport(self.trusted_jwks_uri or "", self.runtime_environment == "local")
        if self.authentication_mode == "entra" and not all(
            (self.entra_tenant_id, self.entra_audience, self.entra_recommendation_client_id)
        ):
            raise ValueError("Entra tenant, audience and Recommendation client ID are required")
        if self.embedding_backend == "azure_openai":
            if not self.azure_openai_endpoint or not self.azure_openai_deployment:
                raise ValueError("Azure OpenAI endpoint and deployment are required")
            if not self.azure_openai_endpoint.startswith("https://"):
                raise ValueError("Azure OpenAI endpoint must use HTTPS")
            if self.azure_openai_endpoint.rstrip("/") != "https://ai-pipesor-dev-04f339b7.services.ai.azure.com":
                raise ValueError("Azure OpenAI endpoint must match ADR-021")
            if self.azure_openai_deployment != "pipesor-dev-embeddings":
                raise ValueError("Azure OpenAI deployment must match ADR-021")
            if self.embedding_model_version == "simulated-v1":
                raise ValueError("a real embedding model version is required")
        return self

    @classmethod
    def from_environment(cls) -> "Settings":
        mapping = {
            "host": "SERVER_ADDRESS", "port": "SERVER_PORT",
            "runtime_environment": "PIPESOR_ENVIRONMENT",
            "storage_backend": "PIPESOR_RAG_STORAGE_BACKEND",
            "database_url": "PIPESOR_DATABASE_URL", "database_username": "PIPESOR_DATABASE_USERNAME",
            "database_password": "PIPESOR_DATABASE_PASSWORD",
            "database_connect_timeout_seconds": "PIPESOR_RAG_DATABASE_CONNECT_TIMEOUT_SECONDS",
            "database_pool_timeout_seconds": "PIPESOR_RAG_DATABASE_POOL_TIMEOUT_SECONDS",
            "database_statement_timeout_ms": "PIPESOR_RAG_DATABASE_STATEMENT_TIMEOUT_MS",
            "hnsw_ef_search": "PIPESOR_RAG_HNSW_EF_SEARCH", "max_request_bytes": "PIPESOR_RAG_MAX_REQUEST_BYTES",
            "authentication_mode": "PIPESOR_RAG_AUTHENTICATION_MODE", "tenant_id": "PIPESOR_TENANT_ID",
            "security_audience": "PIPESOR_SECURITY_AUDIENCE",
            "trusted_workload_id": "PIPESOR_SECURITY_TRUSTEDWORKLOADS_0_ID",
            "trusted_jwks_uri": "PIPESOR_SECURITY_TRUSTEDWORKLOADS_0_JWKSURI",
            "trusted_roles": "PIPESOR_SECURITY_TRUSTEDWORKLOADS_0_ROLES",
            "entra_tenant_id": "PIPESOR_RAG_ENTRA_TENANT_ID", "entra_audience": "PIPESOR_RAG_ENTRA_AUDIENCE",
            "entra_recommendation_client_id": "PIPESOR_RAG_ENTRA_RECOMMENDATION_CLIENT_ID",
            "embedding_backend": "PIPESOR_RAG_EMBEDDING_BACKEND",
            "embedding_model": "PIPESOR_RAG_EMBEDDING_MODEL",
            "embedding_model_version": "PIPESOR_RAG_EMBEDDING_MODEL_VERSION",
            "embedding_dimension": "PIPESOR_RAG_EMBEDDING_DIMENSION",
            "azure_openai_endpoint": "PIPESOR_RAG_AZURE_OPENAI_ENDPOINT",
            "azure_openai_deployment": "PIPESOR_RAG_AZURE_OPENAI_DEPLOYMENT",
            "embedding_timeout_seconds": "PIPESOR_RAG_EMBEDDING_TIMEOUT_SECONDS",
            "embedding_max_retries": "PIPESOR_RAG_EMBEDDING_MAX_RETRIES",
        }
        values = {field: os.environ[name] for field, name in mapping.items() if os.environ.get(name)}
        if "runtime_environment" not in values:
            raise ValueError("PIPESOR_ENVIRONMENT is required")
        values.setdefault("storage_backend", "postgresql")
        values.setdefault("embedding_backend", "azure_openai")
        values.setdefault("authentication_mode", "platform")
        return cls.model_validate(values)


def _transport(value: str, local: bool) -> str:
    from urllib.parse import urlsplit
    parsed = urlsplit(value)
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("JWKS URI must be absolute and contain no credentials")
    if parsed.scheme == "https":
        return value
    if parsed.scheme == "http" and local and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return value
    raise ValueError("HTTPS is required except for local loopback JWKS")
