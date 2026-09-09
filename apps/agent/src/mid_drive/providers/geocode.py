from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .client import request_with_retry

_CACHE: dict[str, "GeocodeHit | None"] = {}


class GeocodeTransportError(RuntimeError):
    """Nominatim timed out or returned a non-success HTTP status."""


@dataclass(frozen=True)
class GeocodeHit:
    query: str
    lat: float
    lng: float
    label: str
    provider: str = "nominatim"


async def geocode(
    nominatim_url: str,
    query: str,
    *,
    countrycodes: str = "in",
    viewbox: str = "76.70,28.95,77.60,28.28",
) -> GeocodeHit | None:
    key = " ".join(query.strip().split()).lower()
    if not key:
        return None
    if key in _CACHE:
        return _CACHE[key]
    url = nominatim_url.rstrip("/") + "/search"
    params = {
        "q": query,
        "format": "json",
        "limit": "1",
        "addressdetails": "1",
        "countrycodes": countrycodes,
        "viewbox": viewbox,
        "bounded": "0",
    }
    try:
        response = await request_with_retry("GET", url, timeout=6.0, params=params)
        rows = response.json()
    except Exception as exc:
        raise GeocodeTransportError(str(exc)) from exc
    if not rows:
        _CACHE[key] = None
        return None
    row = rows[0]
    hit = GeocodeHit(
        query=query,
        lat=float(row["lat"]),
        lng=float(row["lon"]),
        label=str(row.get("display_name") or query).split(",")[0],
    )
    _CACHE[key] = hit
    return hit


async def geocode_pair(
    nominatim_url: str,
    origin_query: str,
    dest_query: str,
    *,
    countrycodes: str = "in",
    viewbox: str = "76.70,28.95,77.60,28.28",
) -> tuple[GeocodeHit | None, GeocodeHit | None]:
    return await asyncio.gather(
        geocode(nominatim_url, origin_query, countrycodes=countrycodes, viewbox=viewbox),
        geocode(nominatim_url, dest_query, countrycodes=countrycodes, viewbox=viewbox),
    )
