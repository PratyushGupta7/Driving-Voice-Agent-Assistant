"""Azure writes Rime lines from an evidence pack. Templates stay the fallback."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from .azure_client import azure_chat, azure_ready
from .speech import sanitize_tts_text

logger = logging.getLogger("mid_drive.speech_compose")

_BANNED = re.compile(
    r"\b(available|occupancy|toll-free|guaranteed|definitely open|space is free)\b",
    re.I,
)
_PROPER = re.compile(r"\b([A-Z][A-Za-z0-9'&.-]*(?:\s+[A-Z][A-Za-z0-9'&.-]*)+)\b")

_SYSTEM = """
You write one or two short spoken sentences for a driving copilot. Rime will read them aloud.
Write for the ear: short clauses, no lists, no markdown, no URLs.
Use ONLY names and facts from the evidence JSON. If a fact is missing, say you do not have it.
Never invent a shop. Never say a parking space is available. Never say the route is toll-free.
Parking is an amenity tag. Tolls are a requested preference.
Do not mention Azure, models, or that you are an AI.
""".strip()


def _allowed_names(evidence: dict[str, Any]) -> set[str]:
    names: set[str] = {
        "cyber hub",
        "gurugram",
        "gurgaon",
        "connaught place",
        "delhi",
        "new delhi",
        "nh 48",
        "iffco chowk",
        "india gate",
    }
    for key in ("name", "area", "brand", "origin_name", "destination_name"):
        value = evidence.get(key)
        if isinstance(value, str) and value.strip():
            names.add(value.strip().lower())
    for item in evidence.get("places") or []:
        if not isinstance(item, dict):
            continue
        for key in ("name", "area", "brand"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                names.add(value.strip().lower())
    return names


def grounding_ok(text: str, evidence: dict[str, Any]) -> bool:
    if not text or _BANNED.search(text):
        return False
    allowed = _allowed_names(evidence)
    for match in _PROPER.finditer(text):
        phrase = match.group(1).strip().lower()
        if phrase in {"gurgaon to delhi", "open street map", "openstreetmap"}:
            continue
        if phrase not in allowed and not any(phrase in name or name in phrase for name in allowed):
            return False
    return True


async def compose_speech(
    settings: Any,
    *,
    purpose: str,
    fallback: str,
    evidence: dict[str, Any],
) -> tuple[str, str, int]:
    """Return (text, source, latency_ms). Always returns speakable text."""
    safe_fallback = sanitize_tts_text(fallback) or fallback
    if not getattr(settings, "azure_speak", False) or not azure_ready(settings):
        return safe_fallback, "template", 0
    timeout = float(getattr(settings, "azure_speak_timeout_s", 1.4) or 1.4)
    started = time.perf_counter()
    raw = await azure_chat(
        settings,
        system=_SYSTEM,
        user=json.dumps({"purpose": purpose, "evidence": evidence, "fallback": safe_fallback}),
        timeout_s=timeout,
        max_tokens=90,
    )
    ms = int((time.perf_counter() - started) * 1000)
    cleaned = sanitize_tts_text(raw or "")
    if not cleaned or not grounding_ok(cleaned, evidence):
        logger.info("azure speak rejected after %sms, using template", ms)
        return safe_fallback, "template", ms
    return cleaned, "azure", ms
