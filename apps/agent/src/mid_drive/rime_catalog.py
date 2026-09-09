from __future__ import annotations

from typing import Any

import httpx

from .config import Settings

_cached_catalog: dict[str, Any] | None = None
_cached_speakers: list[str] | None = None


class RimeCatalogError(RuntimeError):
    pass


def fetch_catalog(url: str, timeout: float = 15.0) -> dict[str, Any]:
    response = httpx.get(url, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RimeCatalogError("Rime catalog was not a JSON object")
    return data


def speakers_for(catalog: dict[str, Any], model: str, language: str) -> list[str]:
    model_block = catalog.get(model)
    if not isinstance(model_block, dict):
        return []
    speakers = model_block.get(language, [])
    return [str(name) for name in speakers] if isinstance(speakers, list) else []


def cache_catalog(settings: Settings) -> list[str]:
    """Fetch once and remember. Prewarm and preflight call this."""
    global _cached_catalog, _cached_speakers
    catalog = fetch_catalog(settings.rime_catalog_url)
    speakers = speakers_for(catalog, settings.rime_model, settings.rime_language)
    if settings.rime_speaker not in speakers:
        preview = ", ".join(speakers[:12]) or "(none)"
        raise RimeCatalogError(
            f"Rime speaker {settings.rime_speaker!r} is not in the live "
            f"{settings.rime_model}/{settings.rime_language} catalog. "
            f"Available (first 12): {preview}"
        )
    _cached_catalog = catalog
    _cached_speakers = speakers
    return speakers


def cached_speakers() -> list[str] | None:
    return _cached_speakers


def assert_speaker_live(settings: Settings, *, require_fresh: bool = False, fail_open: bool = False) -> list[str]:
    """Refuse a stale speaker. After a warm cache, later TTS builds may fail-open."""
    if _cached_speakers is not None and not require_fresh:
        if settings.rime_speaker in _cached_speakers:
            return _cached_speakers
    try:
        return cache_catalog(settings)
    except Exception:
        if fail_open and _cached_speakers is not None and settings.rime_speaker in _cached_speakers:
            return _cached_speakers
        raise
