"""JWKS key cache with per-kid lookup and soft TTL.

Fetches the project JWKS once, caches keys by `kid`, and re-fetches when a
key is not found or the soft TTL (10 min) has elapsed.  Supabase rotates
signing keys at the project level; the kid-miss path ensures running pods
pick up new keys within one bad-token request.
"""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from .config import settings

_cache: dict[str, Any] = {}
_fetched_at: float = 0.0
_TTL = 600  # 10 minutes


def _fetch() -> None:
    global _fetched_at
    url = settings.jwks_url
    if not url:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_JWKS_URL not configured. "
            "Set DEV_MODE=true for local development without Supabase."
        )
    resp = httpx.get(url, timeout=5)
    resp.raise_for_status()
    for key in resp.json().get("keys", []):
        kid = key.get("kid")
        if kid:
            _cache[kid] = key
    _fetched_at = time.monotonic()


def get_key(kid: str) -> dict[str, Any]:
    """Return the JWK dict for *kid*. Refreshes on TTL expiry or kid miss."""
    now = time.monotonic()
    if kid not in _cache or (now - _fetched_at) > _TTL:
        _fetch()
    if kid not in _cache:
        # One forced re-fetch in case this is a freshly rotated key.
        _fetch()
    if kid not in _cache:
        raise KeyError(f"Unknown JWKS kid: {kid!r}")
    return _cache[kid]
