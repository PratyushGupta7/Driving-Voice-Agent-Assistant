from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .config import REPO_ROOT
from .geometry import enrich_route
from .models import MissionConstraints, PlaceCandidate, RouteSnapshot
from .providers.rank import filter_and_rank
from .speech import format_candidate, format_none

FIXTURE_PATH = REPO_ROOT / "fixtures" / "gurgaon-delhi-v1.json"


@lru_cache(maxsize=1)
def load_bundle() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def corridor_snapshot(avoid_tolls: bool = False) -> RouteSnapshot:
    bundle = load_bundle()
    route = bundle["route"]
    origin = route["origin"]
    dest = route["destination"]
    snap = RouteSnapshot(
        origin_name=route["origin_name"],
        destination_name=route["destination_name"],
        origin_lat=origin["lat"],
        origin_lng=origin["lng"],
        dest_lat=dest["lat"],
        dest_lng=dest["lng"],
        geometry=list(route["geometry"]),
        duration_s=route.get("duration_s"),
        distance_m=route.get("distance_m"),
        avoid_tolls=avoid_tolls,
        provider="osrm+fixture",
    )
    return enrich_route(snap)


def all_candidates() -> dict[str, list[PlaceCandidate]]:
    bundle = load_bundle()
    out: dict[str, list[PlaceCandidate]] = {}
    for category, rows in bundle["places"].items():
        out[category] = [
            PlaceCandidate(
                id=row["id"],
                name=row["name"],
                area=row["area"],
                category=category,  # type: ignore[arg-type]
                parking=row.get("parking", "unknown"),
                detour_minutes=row.get("detour_minutes"),
                lat=row.get("lat"),
                lng=row.get("lng"),
                provenance="fixture",
                fixture_version=bundle["id"],
            )
            for row in rows
        ]
    return out


def pick_candidates(
    constraints: MissionConstraints,
    skip_ids: set[str] | None = None,
) -> list[PlaceCandidate]:
    skip = skip_ids or set()
    raw = [item.model_copy() for item in all_candidates().get(constraints.category, [])]
    return filter_and_rank(raw, constraints, skip, corridor_snapshot().geometry)


def pick_candidate(
    constraints: MissionConstraints,
    skip_ids: set[str] | None = None,
) -> PlaceCandidate | None:
    options = pick_candidates(constraints, skip_ids)
    return options[0] if options else None


__all__ = [
    "all_candidates",
    "corridor_snapshot",
    "format_candidate",
    "format_none",
    "load_bundle",
    "pick_candidate",
    "pick_candidates",
]
