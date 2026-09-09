"""Structured Azure helper kept for preflight / debug. Not used on the spoken turn path."""

from __future__ import annotations

import json
import logging
import re

import httpx

from .config import Settings
from .models import MissionConstraints, MissionPatch

logger = logging.getLogger("mid_drive.llm_revision")

_MISSIONISH = re.compile(
    r"\b(find|look for|search|parking|toll|coffee|cafe|caf[eé]|fuel|gas|petrol|"
    r"pharmacy|chemist|detour|minutes|cancel|stop looking|near|destination|"
    r"head to|take me|start from|reroute)\b",
    re.I,
)

_SYSTEM = """
You convert one driver utterance into a mission patch JSON object.
Return only JSON. Never invent place names, travel times, or occupancy.
""".strip()


def worth_llm_fallback(text: str, patch: MissionPatch) -> bool:
    """Always false. Demo NLU is the phrase parser; Azure must not add turn latency."""
    del text, patch
    return False


def would_have_been_fallback(text: str, patch: MissionPatch) -> bool:
    if patch.operation != "unrelated":
        return False
    if len(text.split()) < 4:
        return False
    return bool(_MISSIONISH.search(text))


async def parse_turn_with_llm(
    settings: Settings,
    text: str,
    current: MissionConstraints | None,
    **_kwargs,
) -> MissionPatch | None:
    """Unused on the live turn path. Fail-open if called from a debug tool."""
    url = (
        settings.azure_openai_endpoint.rstrip("/")
        + f"/openai/deployments/{settings.azure_openai_deployment}/chat/completions"
        + f"?api-version={settings.azure_openai_api_version}"
    )
    current_json = current.model_dump() if current else None
    payload = {
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": json.dumps({"utterance": text, "current_constraints": current_json}),
            },
        ],
        "temperature": 0,
        "max_completion_tokens": 180,
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.post(
                url,
                headers={
                    "api-key": settings.azure_openai_api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            patch = MissionPatch.model_validate_json(content)
            if patch.operation in {"create", "replace"} and patch.category is None:
                return MissionPatch(
                    operation="ambiguous",
                    clarification_question="Coffee, fuel, or a pharmacy?",
                )
            return patch
    except Exception as exc:
        logger.info("azure revision helper skipped: %s", exc)
        return None
