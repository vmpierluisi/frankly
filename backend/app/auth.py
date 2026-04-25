"""HTTP Basic auth dependency, gating manager-only routes.

v0 only — see README for v1 upgrade path. Shared password is loaded from env.
"""
from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import settings


_security = HTTPBasic()


def require_manager(
    credentials: HTTPBasicCredentials = Depends(_security),
) -> str:
    """Return the username on success, raise 401 otherwise."""
    correct_user = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        settings.manager_username.encode("utf-8"),
    )
    correct_pass = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        settings.manager_password.encode("utf-8"),
    )
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Manager credentials required.",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
