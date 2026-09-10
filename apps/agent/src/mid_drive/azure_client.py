"""Shared Azure OpenAI chat client. One keep-alive HTTP pool for the process."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from .config import Settings

logger = logging.getLogger("mid_drive.azure")

_CLIENT: httpx.AsyncClient | None = None


def _headers(settings: Settings) -> dict[str, str]:
    return {"api-key": settings.azure_openai_api_key, "Content-Type": "application/json"}


def _url(settings: Settings) -> str:
    return (
        settings.azure_openai_endpoint.rstrip("/")
        + f"/openai/deployments/{settings.azure_openai_deployment}/chat/completions"
        + f"?api-version={settings.azure_openai_api_version}"
    )


def azure_ready(settings: Any) -> bool:
    key = getattr(settings, "azure_openai_api_key", None) if settings else None
    endpoint = getattr(settings, "azure_openai_endpoint", None) if settings else None
    if not key or not endpoint:
        return False
    if str(key).startswith("dummy") or "YOUR_RESOURCE" in str(endpoint):
        return False
    return True


def azure_client() -> httpx.AsyncClient:
    global _CLIENT
    if _CLIENT is None or _CLIENT.is_closed:
        _CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=0.35, read=1.4, write=0.4, pool=0.4),
            limits=httpx.Limits(max_keepalive_connections=8, max_connections=16),
        )
    return _CLIENT


async def azure_chat(
    settings: Settings,
    *,
    system: str,
    user: str,
    timeout_s: float,
    max_tokens: int,
    json_object: bool = False,
) -> str | None:
    if not azure_ready(settings):
        return None
    payload: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "max_completion_tokens": max_tokens,
    }
    if json_object:
        payload["response_format"] = {"type": "json_object"}
    try:
        response = await azure_client().post(
            _url(settings),
            headers=_headers(settings),
            json=payload,
            timeout=timeout_s,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.info("azure chat failed: %s", exc)
        return None


async def azure_chat_json(
    settings: Settings,
    *,
    system: str,
    user: str,
    timeout_s: float,
    max_tokens: int,
) -> dict[str, Any] | None:
    raw = await azure_chat(
        settings,
        system=system,
        user=user,
        timeout_s=timeout_s,
        max_tokens=max_tokens,
        json_object=True,
    )
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.info("azure returned non-json")
        return None
    return data if isinstance(data, dict) else None
