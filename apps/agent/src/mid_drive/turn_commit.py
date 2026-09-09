from __future__ import annotations

import re

from .models import MissionPatch

PTT_FINISHED_IDLE_S = 2.2
OPEN_FINISHED_IDLE_S = 1.5
PTT_SETTLE_S = 0.18
# Kept for older imports; idle now uses the mode-specific delays above.
PARTIAL_IDLE_S = PTT_FINISHED_IDLE_S

_KEEP = re.compile(r"[^a-z0-9 ]+")
_MULTI = re.compile(r"\s+")
_TRAILING_CUT = re.compile(r"(\.{2,}|…|-|—)$")
_ARTICLE_BARE = re.compile(
    r"\b(find|look for|search|need|want|get|sign a)\s+a\s+"
    r"(coffee|caf[eé]|chai|fuel|gas|petrol|pharmacy)\s*$",
    re.I,
)
_HAS_CATEGORY = re.compile(
    r"\b(coffee|caf[eé]|chai|fuel|petrol|gas|pharmacy|chemist)\b",
    re.I,
)
_SEARCH_CLOSER = re.compile(
    r"\b(shop|store|place|pump|station|route|way|along|parking|please|chemist)\b",
    re.I,
)
_SHORT_DONE = re.compile(
    r"\b(keep (this|that|it)|that (one )?works|sounds good|cancel|forget it|never mind|"
    r"another one|another option|not that|somewhere else|first|second|third|avoid (the )?tolls?|"
    r"allow tolls?|needs parking|need parking|parking too|parking required|"
    r"why this|how much extra|does .+ have parking|is there parking|"
    r"any parking|the second one|the first one|the third one|"
    r"where is (it|that)|which area|are they open|compare( them)?|"
    r"what('s| is) the other|other option|what else|what did you find|"
    r"go with |yeh wala|koi aur|parking chahiye)\b",
    re.I,
)
_HANG_LAST = {
    "a",
    "an",
    "the",
    "my",
    "your",
    "our",
    "near",
    "to",
    "for",
    "of",
    "with",
    "and",
    "or",
    "but",
    "wait",
    "find",
    "look",
    "search",
    "is",
    "there",
    "i",
    "we",
    "me",
    "need",
    "want",
}


def normalize_turn(text: str) -> str:
    cleaned = _KEEP.sub(" ", (text or "").lower())
    return _MULTI.sub(" ", cleaned).strip()


def looks_unfinished(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return True
    if _TRAILING_CUT.search(raw):
        return True
    stripped = raw.rstrip(".!?").strip()
    if _ARTICLE_BARE.search(stripped):
        return True
    words = [word for word in normalize_turn(stripped).split() if word]
    if not words:
        return True
    return words[-1] in _HANG_LAST


def looks_finished(text: str) -> bool:
    """True only when the utterance can be answered without cutting the driver off."""
    if looks_unfinished(text):
        return False
    raw = (text or "").strip()
    stripped = raw.rstrip(".!?").strip()
    if _SHORT_DONE.search(stripped):
        return True
    words = [word for word in normalize_turn(stripped).split() if word]
    if raw.endswith("?") and len(words) >= 2:
        return True
    if _HAS_CATEGORY.search(stripped):
        if _SEARCH_CLOSER.search(stripped) or len(words) >= 6:
            return True
        if len(words) <= 3 and not re.search(r"\ba\b", stripped, re.I):
            return True
        return False
    return False


def looks_answerable(text: str, current=None) -> bool:
    """PTT Send / mute flush: commit a complete follow-up even if idle rules are strict."""
    if looks_finished(text):
        return True
    if looks_unfinished(text):
        return False
    from .revision import parse_turn

    patch = parse_turn(text, current)
    return patch.operation != "unrelated"


def looks_commit_ready(text: str) -> bool:
    return looks_finished(text)


def is_duplicate_or_shorter(previous: str, incoming: str) -> bool:
    if not incoming:
        return True
    if incoming == previous:
        return True
    if previous.startswith(incoming):
        return True
    return False


def is_same_utterance(previous: str, incoming: str) -> bool:
    if not previous or not incoming:
        return False
    if incoming == previous or incoming.startswith(previous) or previous.startswith(incoming):
        return True
    prev_words = previous.split()
    next_words = incoming.split()
    take = min(4, len(prev_words), len(next_words))
    return take >= 3 and prev_words[:take] == next_words[:take]


def peel_restated_prefix(text: str, previous: str | None) -> str:
    """ElevenLabs often prepends the last committed sentence to the next turn."""
    if not text or not previous:
        return text
    current = normalize_turn(text)
    prior = normalize_turn(previous)
    if not prior or current == prior or len(prior.split()) < 4:
        return text
    if not current.startswith(prior):
        return text
    rest = current[len(prior) :].strip()
    if len(rest.split()) < 2:
        return text
    return rest


def is_material_followup(patch: MissionPatch) -> bool:
    if patch.operation in {"cancel", "replace", "next", "select", "confirm", "inquire"}:
        return True
    if patch.parking_required is not None or patch.avoid_tolls is not None:
        return True
    if patch.maximum_detour_minutes is not None:
        return True
    if patch.destination_query or patch.origin_query or patch.landmark_query or patch.brand_query:
        return True
    return False
