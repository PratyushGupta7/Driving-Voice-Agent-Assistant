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


_OPENROUTER_SYSTEM = """
You parse a driver's voice utterance into a JSON MissionPatch object for a driving assistant.
Operation MUST be one of: "create", "add", "replace", "cancel", "unrelated", "ambiguous", "confirm", "next", "select", "inquire".
Category MUST be one of: "coffee", "fuel", "pharmacy" (or null if not mentioned or ambiguous).

Rules:
1. "Find coffee", "Find fuel", "Need a pharmacy", "Find petrol pump" -> operation="create", category="coffee"/"fuel"/"pharmacy".
2. "I need parking", "Needs parking", "Avoid tolls", "Near Cyber Hub" -> operation="add", parking_required=true/avoid_tolls=true/landmark_query="...".
3. "Actually fuel", "Switch to coffee" -> operation="replace", category="fuel"/"coffee".
4. "Cancel", "Stop looking", "Forget it" -> operation="cancel".
5. "Keep this one", "Go with this" -> operation="confirm".
6. "Another one", "Next" -> operation="next".
7. "The second one", "Go with Third Wave" -> operation="select", select_index=1 (0-indexed) or select_name="Third Wave Coffee".
8. "Why this one?", "Does it have parking?", "How much extra time?", "Where is it?", "Are they open?" -> operation="inquire", inquire_kind="why"/"parking"/"eta"/"where"/"hours".
9. "Find something near me", "Coffee or fuel?" -> operation="ambiguous", clarification_question="Coffee, fuel, or a pharmacy?".
10. Off-topic utterances like "How is the weather?" -> operation="unrelated".

Return ONLY valid JSON with keys:
"operation", "category", "maximum_detour_minutes", "parking_required", "avoid_tolls", "landmark_query", "destination_query", "origin_query", "brand_query", "select_index", "select_name", "inquire_kind", "clarification_question".
""".strip()


async def parse_turn_with_openrouter(
    settings: Settings,
    text: str,
    current: MissionConstraints | None,
) -> MissionPatch | None:
    if not settings.openrouter_api_key or settings.openrouter_api_key.startswith("dummy"):
        return None
    url = "https://openrouter.ai/api/v1/chat/completions"
    current_json = current.model_dump() if current else None
    payload = {
        "model": settings.openrouter_model or "openai/gpt-4o-mini",
        "messages": [
            {"role": "system", "content": _OPENROUTER_SYSTEM},
            {
                "role": "user",
                "content": json.dumps({"utterance": text, "current_constraints": current_json}),
            },
        ],
        "temperature": 0.0,
        "max_tokens": 180,
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
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
        logger.warning("openrouter LLM parsing failed: %s", exc)
        return None


async def parse_turn_with_llm(
    settings: Settings,
    text: str,
    current: MissionConstraints | None,
    **_kwargs,
) -> MissionPatch | None:
    """Delegates to OpenRouter if openrouter_api_key is set."""
    if settings.openrouter_api_key:
        return await parse_turn_with_openrouter(settings, text, current)
    return None
