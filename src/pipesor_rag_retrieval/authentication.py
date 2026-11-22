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
    scheme_name="WorkloadBearer",
    description="Platform or Entra app-only token for the RAG audience with the Rag.Query role.",
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


class PlatformInternalCaller:
    RECOMMENDATION_ID = "970e0ca6-7657-5cc0-a671-ee41c78a5214"

    def __init__(self, tenant_id: UUID, jwks_uri: str, *, decoder=None) -> None:
        self.tenant_id = str(tenant_id)
        self.issuer = "urn:pipesor:workload:recommendation"
        self.audience = "urn:pipesor:api:rag"
        self._decoder = decoder or self._build_decoder(jwks_uri)

    def _build_decoder(self, jwks_uri: str):
        keys = jwt.PyJWKClient(jwks_uri, cache_keys=True, cache_jwk_set=True, lifespan=300, timeout=5)

        def decode(token: str) -> dict[str, Any]:
            key = keys.get_signing_key_from_jwt(token)
            return jwt.decode(
                token, key.key, algorithms=["RS256"], audience=self.audience, issuer=self.issuer,
                leeway=60, options={"require": ["exp", "iat", "nbf", "tid", "oid", "azp", "sub", "roles", "idtyp", "ver", "jti"]},
            )
        return decode

    def __call__(
        self,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Security(ENTRA_BEARER_SCHEME)],
    ) -> str:
        if credentials is None or credentials.scheme.casefold() != "bearer":
            raise HTTPException(status_code=401, detail="invalid_access_token", headers={"WWW-Authenticate": "Bearer"})
        try:
            claims = self._decoder(credentials.credentials)
            issued, expires, not_before = (int(claims[name]) for name in ("iat", "exp", "nbf"))
            roles = claims.get("roles")
            valid = (
                claims.get("tid") == self.tenant_id and claims.get("idtyp") == "app"
                and claims.get("ver") == "2.0" and "scp" not in claims
                and expires >= issued and expires - issued <= 300 and not_before <= expires
                and isinstance(claims.get("jti"), str)
            )
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=401, detail="invalid_access_token", headers={"WWW-Authenticate": "Bearer"}) from error
        if not valid:
            raise HTTPException(status_code=401, detail="invalid_access_token", headers={"WWW-Authenticate": "Bearer"})
        principal = self.RECOMMENDATION_ID
        caller_ok = all(claims.get(name) == principal for name in ("oid", "azp", "sub"))
        role_ok = isinstance(roles, list) and roles == ["Rag.Query"]
        if not caller_ok or not role_ok:
            raise HTTPException(status_code=403, detail="caller_not_authorized")
        return principal


def build_internal_caller(settings: Settings) -> Callable[..., str]:
    if settings.authentication_mode == "test":
        return SimulatedInternalCaller("recommendation_service")
    if settings.authentication_mode == "platform":
        assert settings.tenant_id is not None and settings.trusted_jwks_uri is not None
        return PlatformInternalCaller(settings.tenant_id, settings.trusted_jwks_uri)
    assert settings.entra_tenant_id is not None
    assert settings.entra_audience is not None
    assert settings.entra_recommendation_client_id is not None
    return EntraInternalCaller(
        settings.entra_tenant_id,
        settings.entra_audience,
        settings.entra_recommendation_client_id,
        settings.entra_required_role,
    )
