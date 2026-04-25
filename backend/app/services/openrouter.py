"""OpenRouter client — OpenAI-compatible Chat Completions with strict JSON.

Per the brief, every LLM call goes through this wrapper with:
  * response_format: {"type": "json_schema", "json_schema": {...}, "strict": true}
  * The `response-healing` plugin enabled (OpenRouter repairs model output
    that doesn't conform to the schema).

The default model is read from OPENROUTER_MODEL so it's swappable without code
changes. Any OpenAI-compatible model on OpenRouter works.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(RuntimeError):
    """Raised when the upstream call fails or the response is unusable."""


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
            resp = await client.post(_OPENROUTER_URL, json=payload, headers=headers)
        except httpx.HTTPError as e:
            raise OpenRouterError(f"Network error calling OpenRouter: {e}") from e

    if resp.status_code >= 400:
        raise OpenRouterError(
            f"OpenRouter returned {resp.status_code}: {resp.text[:500]}"
        )

    body = resp.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise OpenRouterError(f"Unexpected OpenRouter response shape: {body}") from e

    # With strict JSON schema the content is a JSON-encoded string.
    if isinstance(content, dict):
        return content  # some providers already return a dict
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise OpenRouterError(
            f"OpenRouter returned non-JSON content despite strict schema: "
            f"{content[:500]}"
        ) from e
