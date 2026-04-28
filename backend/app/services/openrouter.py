"""OpenRouter client — OpenAI-compatible Chat Completions with strict JSON.

Per the brief, every LLM call goes through this wrapper with:
  * response_format: {"type": "json_schema", "json_schema": {...}, "strict": true}
  * The `response-healing` plugin enabled (OpenRouter repairs model output
    that doesn't conform to the schema).

The default model is read from OPENROUTER_MODEL so it's swappable without code
changes. Any OpenAI-compatible model on OpenRouter works.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Global concurrency cap — prevents OpenRouter rate-limit spikes under heavy
# parallel load (e.g. /matches/search running alongside rollouts).
_GLOBAL_OPENROUTER_SEM = asyncio.Semaphore(
    int(os.environ.get("OPENROUTER_GLOBAL_CONCURRENCY", "16"))
)

_RETRY_DELAYS = (1.0, 2.0, 4.0)  # 3 retries; 7s total worst-case wait


class OpenRouterError(RuntimeError):
    """Raised when the upstream call fails or the response is unusable."""


class RetryableError(OpenRouterError):
    """Raised on conditions worth retrying (429, 5xx, transient network failures)."""


class FatalError(OpenRouterError):
    """Raised on conditions where retry will not help (4xx other than 429,
    schema-mismatch after healing exhausted)."""


async def chat_json_with_retry(
    *args, max_attempts: int = 4, **kwargs
) -> dict[str, Any]:
    """Thin retry wrapper around chat_json with exponential backoff."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await chat_json(*args, **kwargs)
        except RetryableError as e:
            last_exc = e
            if attempt + 1 >= max_attempts:
                break
            await asyncio.sleep(_RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)])
        except FatalError:
            raise
    raise last_exc  # surface the last retryable failure


async def chat_json(
    *,
    system: str,
    user: str,
    schema: dict[str, Any],
    schema_name: str,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2000,
) -> dict[str, Any]:
    """Call OpenRouter; return the parsed JSON object.

    Parameters
    ----------
    system, user : str
        The two messages. We keep it simple — no multi-turn here.
    schema : dict
        JSON Schema the model's output MUST match. Pass the full schema object
        (type/properties/required/additionalProperties=False, etc.).
    schema_name : str
        Short identifier sent to OpenRouter as the response_format name.
    model : str, optional
        Override the default (settings.openrouter_model).

    Notes
    -----
    Attaches a ``_usage`` key to the returned dict (prompt_tokens,
    completion_tokens, total_tokens) so callers can track cost without
    parsing the raw response themselves. Downstream callers that don't need
    it can safely ignore the extra key.
    """
    if not settings.openrouter_api_key:
        raise OpenRouterError(
            "OPENROUTER_API_KEY is not set. Configure it in .env before "
            "running LLM-backed routes."
        )

    payload: dict[str, Any] = {
        "model": model or settings.openrouter_model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        },
        # OpenRouter's response-healing plugin: repairs malformed JSON so we
        # don't blow up on the occasional off-schema emission.
        "plugins": [{"id": "response-healing"}],
    }

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.openrouter_http_referer,
        "X-Title": settings.openrouter_x_title,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0)) as client:
        try:
            async with _GLOBAL_OPENROUTER_SEM:
                resp = await client.post(_OPENROUTER_URL, json=payload, headers=headers)
        except httpx.HTTPError as e:
            raise RetryableError(f"Network error calling OpenRouter: {e}") from e

    _RETRYABLE_STATUS = {429, 502, 503, 504}
    if resp.status_code in _RETRYABLE_STATUS:
        raise RetryableError(
            f"OpenRouter returned {resp.status_code}: {resp.text[:500]}"
        )
    if resp.status_code >= 400:
        raise FatalError(
            f"OpenRouter returned {resp.status_code}: {resp.text[:500]}"
        )

    body = resp.json()
    usage = body.get("usage", {})

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise FatalError(f"Unexpected OpenRouter response shape: {body}") from e

    # With strict JSON schema the content is a JSON-encoded string.
    if isinstance(content, dict):
        result = content
    else:
        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            # Healing plugin has already retried — treat as fatal.
            raise FatalError(
                f"OpenRouter returned non-JSON content despite strict schema: "
                f"{content[:500]}"
            ) from e

    result["_usage"] = usage
    return result
