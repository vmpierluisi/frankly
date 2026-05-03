"""Supabase Storage downloader.

Used by the profile-extraction pipeline to fetch CV files (and any future
candidate-uploaded artefacts) by their bucket key. Uses the service-role
secret so it bypasses RLS — every caller must already be authorized to
touch the candidate row.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


_DEFAULT_TIMEOUT = 20.0
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB cap on single artefact


class SupabaseStorageError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.supabase_url and settings.supabase_secret_key)


def download(bucket: str, path: str) -> bytes:
    """Fetch the bytes of an object from a Supabase Storage bucket.

    Raises SupabaseStorageError on misconfiguration, HTTP error, or oversize
    payload. The caller is responsible for catching + degrading gracefully.
    """
    if not is_configured():
        raise SupabaseStorageError(
            "Supabase Storage is not configured (supabase_url / supabase_secret_key empty)."
        )

    url = f"{settings.supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_secret_key}",
        "apikey": settings.supabase_secret_key,
    }

    try:
        with httpx.Client(timeout=_DEFAULT_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise SupabaseStorageError(f"Storage fetch failed: {exc}") from exc

    if resp.status_code == 404:
        raise SupabaseStorageError(f"Object not found: {bucket}/{path}")
    if resp.status_code >= 400:
        raise SupabaseStorageError(
            f"Storage fetch returned {resp.status_code}: {resp.text[:200]}"
        )

    body = resp.content
    if len(body) > _MAX_BYTES:
        raise SupabaseStorageError(
            f"Artefact too large ({len(body)} bytes > {_MAX_BYTES})."
        )
    return body
