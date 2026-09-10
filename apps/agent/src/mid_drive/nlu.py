from __future__ import annotations

import logging
import re
import time
from typing import Any

from .llm_revision import (
    parse_turn_with_llm,
    prefer_rules_over_llm,
    residual_parse,
    rules_confident,
)
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
    "juice",
    "smoothie",
    "shop",
    "petrol",
    "pump",
    "pharmacy",
    "store",
    "roasters",
}


def nlu_mode(settings: Any) -> str:
    raw = getattr(settings, "nlu_mode", None) if settings else None
    if raw in {"hybrid", "azure"}:
        return raw
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
) -> tuple[MissionPatch, str, int]:
    """Rules first. Azure only when the mode asks for it or the grammar is weak."""
    del prefs
    started = time.perf_counter()
    rules = sanitize_patch(parse_turn(text, current), text, offered)
    mode = nlu_mode(settings)

    if mode == "rules":
        return rules, "rules", int((time.perf_counter() - started) * 1000)

    need_llm = mode == "azure" or residual_parse(text, rules)
    if mode == "hybrid" and rules_confident(rules) and not need_llm:
        return rules, "rules", int((time.perf_counter() - started) * 1000)

    try:
        llm_patch = await parse_turn_with_llm(settings, text, current)
    except Exception as exc:
        logger.warning("azure resolve failed, using rules: %s", exc)
        llm_patch = None

    if llm_patch is None or prefer_rules_over_llm(rules, llm_patch):
        source = "rules"
        patch = rules
    else:
        source = "azure"
        patch = sanitize_patch(llm_patch, text, offered)
    return patch, source, int((time.perf_counter() - started) * 1000)
