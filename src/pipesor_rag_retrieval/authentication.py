from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from .configuration import Settings


SIMULATED_CALLER_SCHEME = APIKeyHeader(
    name="X-Pipesor-Caller",
    scheme_name="SimulatedInternalCaller",
    description="Local/test adapter only; production uses Microsoft Entra bearer tokens.",
    auto_error=False,
)
ENTRA_BEARER_SCHEME = HTTPBearer(
    scheme_name="EntraBearer",
    description="Single-tenant app-only token for the RAG audience with the Rag.Query role.",
    auto_error=False,
)


class SimulatedInternalCaller:
    def __init__(self, expected: str) -> None:
        self.expected = expected

    def __call__(self, api_key: str | None = Security(SIMULATED_CALLER_SCHEME)) -> str:
        if api_key != self.expected:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="caller_not_authorized")
        return api_key


class EntraInternalCaller:
    def __init__(
        self,
        tenant_id: UUID,
        audience: UUID,
        recommendation_client_id: UUID,
        required_role: str,
        *,
        decoder: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self.tenant_id = str(tenant_id)
        self.audience = str(audience)
        self.recommendation_client_id = str(recommendation_client_id)
        self.required_role = required_role
        self.issuer = f"https://login.microsoftonline.com/{self.tenant_id}/v2.0"
        self._decoder = decoder or self._build_decoder()

    def _build_decoder(self) -> Callable[[str], dict[str, Any]]:
        keys = jwt.PyJWKClient(
            f"https://login.microsoftonline.com/{self.tenant_id}/discovery/v2.0/keys",
            cache_keys=True,
            lifespan=300,
            timeout=5,
        )

        def decode(token: str) -> dict[str, Any]:
            signing_key = keys.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "nbf", "tid", "azp", "roles", "idtyp"]},
            )

        return decode

    def __call__(
        self,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Security(ENTRA_BEARER_SCHEME)],
    ) -> str:
        if credentials is None or credentials.scheme.casefold() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid_access_token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            claims = self._decoder(credentials.credentials)
        except jwt.PyJWTError as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid_access_token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from error
        roles = claims.get("roles")
        authorized = (
            claims.get("tid") == self.tenant_id
            and claims.get("azp") == self.recommendation_client_id
            and claims.get("idtyp") == "app"
            and "scp" not in claims
            and isinstance(roles, list)
            and self.required_role in roles
        )
        if not authorized:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="caller_not_authorized")
        return self.recommendation_client_id


def build_internal_caller(settings: Settings) -> Callable[..., str]:
    if settings.authentication_mode == "simulated":
        return SimulatedInternalCaller("recommendation_service")
    assert settings.entra_tenant_id is not None
    assert settings.entra_audience is not None
    assert settings.entra_recommendation_client_id is not None
    return EntraInternalCaller(
        settings.entra_tenant_id,
        settings.entra_audience,
        settings.entra_recommendation_client_id,
        settings.entra_required_role,
    )
