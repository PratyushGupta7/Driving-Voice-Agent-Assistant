from __future__ import annotations

import logging
import re
from typing import Any

from .llm_revision import parse_turn_with_openrouter
from .models import MissionConstraints, MissionPatch, PlaceCandidate, SessionPrefs
from .revision import parse_turn

logger = logging.getLogger("mid_drive.nlu")

_KEEP = re.compile(r"[^a-z0-9]+")
_GENERIC = {
    "a",
    "an",
    "the",
    "of",
    "near",
    "in",
    "at",
    "on",
    "to",
    "for",
    "coffee",
    "cafe",
    "shop",
    "petrol",
    "pump",
    "pharmacy",
    "store",
    "roasters",
}


def nlu_mode(settings: Any) -> str:
    if settings and getattr(settings, "openrouter_api_key", None):
        return "openrouter"
    return "rules"


def _norm(text: str) -> str:
    return _KEEP.sub(" ", (text or "").lower()).strip()


def _in_text(needle: str | None, text: str) -> bool:
    if not needle:
        return False
    blob = _norm(needle)
    hay = _norm(text)
    if blob and blob in hay:
        return True
    tokens = [part for part in blob.split() if part not in _GENERIC]
    hay_tokens = set(hay.split())
    return bool(tokens) and all(part in hay_tokens for part in tokens)


def _offered_match(name: str | None, offered: list[PlaceCandidate]) -> bool:
    if not name or not offered:
        return False
    needle = _norm(name)
    if not needle:
        return False
    for item in offered:
        blob = _norm(" ".join(part for part in (item.name, item.brand, item.area) if part))
        if needle in blob or _norm(item.name) in needle or needle in _norm(item.name):
            return True
    return False


def sanitize_patch(
    patch: MissionPatch,
    text: str,
    offered: list[PlaceCandidate] | None = None,
) -> MissionPatch:
    """Drop fields the driver did not say. Never invent a shop name."""
    places = offered or []
    updates: dict[str, Any] = {}
    for field in ("brand_query", "landmark_query", "destination_query", "origin_query"):
        value = getattr(patch, field)
        if value and not _in_text(value, text):
            updates[field] = None
    if patch.operation == "inquire" and patch.inquire_kind is None:
        updates["inquire_kind"] = "why"
    if patch.operation != "inquire":
        updates["inquire_kind"] = None
    if patch.operation != "select":
        updates["select_index"] = None
        updates["select_name"] = None
    elif patch.select_name and not _offered_match(patch.select_name, places) and not _in_text(
        patch.select_name, text
    ):
        updates["select_name"] = None
    if patch.operation not in {"create", "replace", "add", "next", "ambiguous"}:
        updates["clarification_question"] = None
    return patch.model_copy(update=updates) if updates else patch


async def resolve_patch(
    settings: Any,
    text: str,
    current: MissionConstraints | None,
    *,
    offered: list[PlaceCandidate] | None = None,
    prefs: SessionPrefs | None = None,
) -> tuple[MissionPatch, str]:
    del prefs
    if settings and getattr(settings, "openrouter_api_key", None):
        try:
            llm_patch = await parse_turn_with_openrouter(settings, text, current)
            if llm_patch and llm_patch.operation != "unrelated":
                return sanitize_patch(llm_patch, text, offered), "openrouter"
        except Exception as exc:
            logger.warning("openrouter resolve failed, falling back to rules: %s", exc)
    patch = parse_turn(text, current)
    return sanitize_patch(patch, text, offered), "rules"
