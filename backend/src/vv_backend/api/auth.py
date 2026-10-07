"""Clerk session-token verification and role checks.

Checks (SECURITY.md): RS256 signature against Clerk's JWKS, `exp`/`nbf` (small
leeway for clock skew), `iss` = our Clerk instance, `azp` in our authorized
parties, `sub` present. The role comes only from the verified token's `role`
claim (Clerk session-token template: "role": "{{user.public_metadata.role}}"),
never from request data. Unknown or missing roles mean "learner".

Tokens are never logged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Protocol

import jwt
from fastapi import Depends, HTTPException, Request, status

from ..content import Actor, Role
from .settings import Settings

LEEWAY_S = 5


class KeyProvider(Protocol):
    def signing_key(self, token: str): ...


class ClerkJWKS:
    """Fetches and caches Clerk's public keys (PyJWKClient caches per process)."""

    def __init__(self, url: str):
        self._client = jwt.PyJWKClient(url, cache_keys=True, lifespan=3600, timeout=5)

    def signing_key(self, token: str):
        return self._client.get_signing_key_from_jwt(token).key


class StaticJWKS:
    """Keys from a JWKS document (tests, and local dev via vv_backend.devtools)."""

    def __init__(self, jwks: dict):
        self._keys = {k["kid"]: jwt.PyJWK(k).key for k in jwks["keys"]}

    @classmethod
    def from_file(cls, path: str) -> StaticJWKS:
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def signing_key(self, token: str):
        kid = jwt.get_unverified_header(token).get("kid")
        if kid not in self._keys:
            raise jwt.InvalidTokenError("unknown key id")
        return self._keys[kid]


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    clerk_id: str
    role: Role

    @property
    def actor(self) -> Actor:
        return Actor(self.clerk_id, self.role)


def verify_token(token: str, settings: Settings, keys: KeyProvider) -> Principal:
    try:
        claims = jwt.decode(
            token,
            key=keys.signing_key(token),
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            leeway=LEEWAY_S,
            options={"require": ["exp", "iat", "iss", "sub"], "verify_aud": False},
        )
    except jwt.PyJWKClientError as e:
        raise AuthError("signing keys unavailable") from e
    except jwt.InvalidTokenError as e:
        raise AuthError(type(e).__name__) from e
    if claims.get("azp") not in settings.authorized_parties:
        raise AuthError("unauthorized party")
    try:
        role = Role(claims.get("role") or "learner")
    except ValueError:
        role = Role.LEARNER
    return Principal(clerk_id=str(claims["sub"]), role=role)


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def current_principal(request: Request) -> Principal:
    token = _bearer(request)
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token",
                            headers={"WWW-Authenticate": "Bearer"})  # fmt: skip
    state = request.app.state
    try:
        return verify_token(token, state.settings, state.keys)
    except AuthError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token",
                            headers={"WWW-Authenticate": "Bearer"}) from e  # fmt: skip


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def require_roles(*roles: Role):
    def dep(principal: CurrentPrincipal) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
        return principal

    return dep


Staff = Annotated[Principal, Depends(require_roles(Role.ADMIN, Role.ADVISOR))]
Advisor = Annotated[Principal, Depends(require_roles(Role.ADVISOR))]
