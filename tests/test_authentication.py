from __future__ import annotations

from typing import Any
from uuid import UUID

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from pipesor_rag_retrieval.authentication import EntraInternalCaller


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
