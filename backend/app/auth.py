"""FastAPI auth dependencies — Supabase JWT (JWKS / ES256 or RS256).

Three public deps:
  require_user      — any authenticated Supabase user
  require_manager   — user whose email is in MANAGER_EMAILS
  require_candidate — user whose email is NOT in MANAGER_EMAILS

When DEV_MODE=true all checks are bypassed and a synthetic manager identity
is returned so the backend works without a Supabase project during local dev.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import jwt
from jwt.algorithms import ECAlgorithm, RSAAlgorithm
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import _jwks_cache
from .config import settings

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    auth_user_id: str
    email: str
    role: str  # "manager" | "candidate"


_DEV_USER = CurrentUser(
    auth_user_id="dev-local",
    email="dev@local.dev",
    role="manager",
)


def _public_key_for_jwk(jwk: dict, alg: str):
    jwk_str = json.dumps(jwk)
    if alg == "ES256":
        return ECAlgorithm.from_jwk(jwk_str)
    return RSAAlgorithm.from_jwk(jwk_str)


def _decode(token: str) -> CurrentUser:
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid", "")
        alg = header.get("alg", "RS256")
        jwk = _jwks_cache.get_key(kid)
        public_key = _public_key_for_jwk(jwk, alg)
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            options={"verify_iss": False},
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token signing key not found: {exc}",
        ) from exc
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        ) from exc

    email = (payload.get("email") or "").lower()
    role = "manager" if email in settings.manager_email_set else "candidate"
    return CurrentUser(
        auth_user_id=payload.get("sub", ""),
        email=email,
        role=role,
    )


def require_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    if settings.dev_mode:
        return _DEV_USER
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required.",
        )
    return _decode(creds.credentials)


def require_manager(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    if user.role != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager role required.",
        )
    return user


def require_candidate(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    if user.role != "candidate":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Candidate role required.",
        )
    return user
