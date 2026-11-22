from __future__ import annotations

from typing import Any
from uuid import UUID

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from pipesor_rag_retrieval.authentication import EntraInternalCaller, PlatformInternalCaller


TENANT = UUID("11111111-1111-4111-8111-111111111111")
AUDIENCE = UUID("22222222-2222-4222-8222-222222222222")
RECOMMENDATION = UUID("33333333-3333-4333-8333-333333333333")


def credentials() -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials="synthetic-token")


def claims(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "tid": str(TENANT),
        "azp": str(RECOMMENDATION),
        "idtyp": "app",
        "roles": ["Rag.Query"],
    }
    value.update(overrides)
    return value


def caller(payload: dict[str, Any]) -> EntraInternalCaller:
    return EntraInternalCaller(
        TENANT,
        AUDIENCE,
        RECOMMENDATION,
        "Rag.Query",
        decoder=lambda _: payload,
    )


def test_accepts_only_authorized_recommendation_app_token() -> None:
    assert caller(claims())(credentials()) == str(RECOMMENDATION)


@pytest.mark.parametrize(
    "payload",
    (
        claims(tid="99999999-9999-4999-8999-999999999999"),
        claims(azp="99999999-9999-4999-8999-999999999999"),
        claims(idtyp="user"),
        claims(roles=["Other.Role"]),
        claims(scp="Rag.Query"),
    ),
)
def test_rejects_wrong_tenant_actor_token_type_role_or_delegation(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(HTTPException) as captured:
        caller(payload)(credentials())
    assert captured.value.status_code == 403
    assert captured.value.detail == "caller_not_authorized"


def test_rejects_missing_or_invalid_token_as_unauthenticated() -> None:
    entra = EntraInternalCaller(
        TENANT,
        AUDIENCE,
        RECOMMENDATION,
        "Rag.Query",
        decoder=lambda _: (_ for _ in ()).throw(jwt.InvalidTokenError("synthetic")),
    )
    with pytest.raises(HTTPException) as missing:
        entra(None)
    with pytest.raises(HTTPException) as invalid:
        entra(credentials())
    assert missing.value.status_code == 401
    assert invalid.value.status_code == 401
    assert invalid.value.headers == {"WWW-Authenticate": "Bearer"}


PLATFORM_ID = "970e0ca6-7657-5cc0-a671-ee41c78a5214"


def platform_claims(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "iss": "urn:pipesor:workload:recommendation",
        "aud": "urn:pipesor:api:rag",
        "tid": str(TENANT),
        "oid": PLATFORM_ID,
        "azp": PLATFORM_ID,
        "sub": PLATFORM_ID,
        "roles": ["Rag.Query"],
        "idtyp": "app",
        "ver": "2.0",
        "iat": 1000,
        "nbf": 1000,
        "exp": 1300,
        "jti": "test-jti",
    }
    value.update(overrides)
    return value


def platform(payload: dict[str, Any]) -> PlatformInternalCaller:
    return PlatformInternalCaller(TENANT, "http://127.0.0.1:8086/.well-known/jwks.json", decoder=lambda _: payload)


def test_platform_accepts_exact_recommendation_contract() -> None:
    assert platform(platform_claims())(credentials()) == PLATFORM_ID


@pytest.mark.parametrize(
    "payload",
    (
        platform_claims(tid="99999999-9999-4999-8999-999999999999"),
        platform_claims(idtyp="user"),
        platform_claims(ver="1.0"),
        platform_claims(scp="Rag.Query"),
        platform_claims(exp=1301),
        platform_claims(jti=None),
    ),
)
def test_platform_invalid_token_claims_are_unauthenticated(payload: dict[str, Any]) -> None:
    with pytest.raises(HTTPException) as captured:
        platform(payload)(credentials())
    assert captured.value.status_code == 401


@pytest.mark.parametrize(
    "payload",
    (
        platform_claims(oid="99999999-9999-4999-8999-999999999999"),
        platform_claims(roles=["Other.Role"]),
        platform_claims(roles=["Rag.Query", "Other.Role"]),
    ),
)
def test_platform_wrong_caller_or_role_is_forbidden(payload: dict[str, Any]) -> None:
    with pytest.raises(HTTPException) as captured:
        platform(payload)(credentials())
    assert captured.value.status_code == 403
