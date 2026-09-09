from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from ..fixtures_data import all_candidates, corridor_snapshot, format_candidate, format_none
from ..models import MissionConstraints, PlaceCandidate, RouteSnapshot
from .geocode import GeocodeTransportError, geocode, geocode_pair
from .osrm import OsrmRouter, settings_key
from .overpass import OverpassPlaces
from .rank import filter_and_rank

logger = logging.getLogger("mid_drive.plan")


@dataclass
class PlanOutcome:
    candidate: PlaceCandidate | None
    alternatives: list[PlaceCandidate]
    route: RouteSnapshot
    places_cache: list[PlaceCandidate] = field(default_factory=list)
    provider: str = "fixture"
    fallback_used: bool = False
    spoken: str = ""
    transport_failed: bool = False


def _spoken(
    constraints: MissionConstraints,
    candidate: PlaceCandidate | None,
    fallback: bool,
    alternatives: list[PlaceCandidate] | None = None,
) -> str:
    if candidate is None:
        text = format_none()
    else:
        text = format_candidate(constraints, candidate, alternatives)
    if fallback:
        return "Live maps did not answer in time, so I used the saved corridor. " + text
    return text


def _geo_kwargs(settings) -> dict[str, str]:
    return {
        "countrycodes": getattr(settings, "nominatim_countrycodes", "in"),
        "viewbox": getattr(settings, "nominatim_viewbox", "76.70,28.95,77.60,28.28"),
    }


def _note_detour(item: PlaceCandidate) -> None:
    if item.verified and item.detour_minutes:
        line = f"the extra time is about {item.detour_minutes} minutes"
        if line not in item.reasons:
            item.reasons = [line, *item.reasons]


def _baked_ends(constraints: MissionConstraints, origin_q: str, dest_q: str) -> RouteSnapshot:
    route = corridor_snapshot(constraints.avoid_tolls)
    route.origin_query = origin_q
    route.dest_query = dest_q
    route.settings_hash = settings_key(constraints.avoid_tolls)
    return route


async def resolve_endpoints(
    settings,
    constraints: MissionConstraints,
) -> tuple[str, str, RouteSnapshot]:
    origin_q = constraints.origin_query or settings.route_origin
    dest_q = constraints.destination_query or settings.route_destination
    baked = _baked_ends(constraints, origin_q, dest_q)
    try:
        origin, dest = await geocode_pair(settings.nominatim_url, origin_q, dest_q, **_geo_kwargs(settings))
    except GeocodeTransportError:
        if constraints.origin_query or constraints.destination_query:
            raise
        return origin_q, dest_q, baked
    if constraints.origin_query and origin is None:
        raise ValueError("origin_not_found")
    if constraints.destination_query and dest is None:
        raise ValueError("destination_not_found")
    if origin and dest:
        return (
            origin_q,
            dest_q,
            RouteSnapshot(
                origin_name=origin.label,
                destination_name=dest.label,
                origin_lat=origin.lat,
                origin_lng=origin.lng,
                dest_lat=dest.lat,
                dest_lng=dest.lng,
                avoid_tolls=constraints.avoid_tolls,
                origin_query=origin_q,
                dest_query=dest_q,
                settings_hash=settings_key(constraints.avoid_tolls),
                provider="nominatim",
            ),
        )
    return origin_q, dest_q, baked


def _can_reuse_route(
    reuse: RouteSnapshot | None,
    constraints: MissionConstraints,
    dest_q: str,
    origin_q: str,
) -> bool:
    if reuse is None:
        return False
    if reuse.settings_hash != settings_key(constraints.avoid_tolls):
        return False
    if reuse.dest_query and reuse.dest_query != dest_q:
        return False
    if reuse.origin_query and reuse.origin_query != origin_q:
        return False
    return True


async def live_plan(
    settings,
    constraints: MissionConstraints,
    skip_ids: set[str],
    reuse_route: RouteSnapshot | None,
    reuse_places: list[PlaceCandidate] | None,
) -> PlanOutcome:
    router = OsrmRouter(settings.osrm_url)
    origin_q, dest_q, ends = await resolve_endpoints(settings, constraints)
    baseline = reuse_route if _can_reuse_route(reuse_route, constraints, dest_q, origin_q) else None
    if baseline is None:
        baseline = await router.baseline(
            (ends.origin_lat, ends.origin_lng),
            (ends.dest_lat, ends.dest_lng),
            avoid_tolls=constraints.avoid_tolls,
            origin_name=ends.origin_name,
            dest_name=ends.destination_name,
            origin_query=origin_q,
            dest_query=dest_q,
        )
        if baseline is None:
            raise RuntimeError("osrm_baseline_failed")
        if constraints.avoid_tolls:
            open_route = await router.baseline(
                (ends.origin_lat, ends.origin_lng),
                (ends.dest_lat, ends.dest_lng),
                avoid_tolls=False,
                origin_name=ends.origin_name,
                dest_name=ends.destination_name,
                origin_query=origin_q,
                dest_query=dest_q,
            )
            if open_route and open_route.duration_s and baseline.duration_s:
                extra = max(0, int(baseline.duration_s) - int(open_route.duration_s))
                baseline.toll_compare_minutes = round(extra / 60) or None

    raw_places = reuse_places
    if raw_places is None:
        overpass = OverpassPlaces(settings.overpass_url)
        raw_places = await overpass.along_route(constraints.category, baseline.geometry)

    landmark = None
    landmark_miss = False
    if constraints.landmark_query:
        try:
            hit = await geocode(settings.nominatim_url, constraints.landmark_query, **_geo_kwargs(settings))
            if hit:
                landmark = (hit.lat, hit.lng)
            else:
                landmark_miss = True
        except GeocodeTransportError:
            landmark_miss = True

    ranked = filter_and_rank(raw_places, constraints, skip_ids, baseline.geometry, landmark)

    async def _verify(item: PlaceCandidate) -> tuple[PlaceCandidate, RouteSnapshot | None]:
        return item, await router.via(baseline, item)

    batch = ranked[:6]
    checks = await asyncio.gather(*[_verify(item) for item in batch], return_exceptions=True)
    verified: PlaceCandidate | None = None
    via_route = baseline
    alts: list[PlaceCandidate] = []
    for result in checks:
        if isinstance(result, BaseException):
            continue
        item, routed = result
        if routed is None:
            continue
        extra = max(0, int(routed.duration_s or 0) - int(baseline.duration_s or 0))
        item.detour_minutes = round(extra / 60)
        if (
            constraints.maximum_detour_minutes is not None
            and item.detour_minutes > constraints.maximum_detour_minutes
        ):
            continue
        item.verified = True
        item.extra_vs_baseline_s = extra
        _note_detour(item)
        if verified is None:
            verified = item
            via_route = routed.model_copy()
            via_route.geometry = list(baseline.geometry)
            via_route.via_geometry = list(routed.geometry)
        else:
            alts.append(item)

    prefix = ""
    if landmark_miss and constraints.landmark_query:
        prefix = "I could not pin that landmark, so I stayed on the corridor. "
    if verified is None:
        return PlanOutcome(
            candidate=None,
            alternatives=[],
            route=baseline,
            places_cache=raw_places,
            provider="overpass+osrm",
            spoken=prefix + format_none(),
        )
    return PlanOutcome(
        candidate=verified,
        alternatives=alts[:3],
        route=via_route,
        places_cache=raw_places,
        provider="overpass+osrm",
        spoken=prefix + _spoken(constraints, verified, False, alts[:3]),
    )


def fixture_plan(
    constraints: MissionConstraints,
    skip_ids: set[str],
) -> PlanOutcome:
    route = corridor_snapshot(constraints.avoid_tolls)
    route.settings_hash = settings_key(constraints.avoid_tolls)
    raw = [item.model_copy() for item in all_candidates().get(constraints.category, [])]
    ranked = filter_and_rank(raw, constraints, skip_ids, route.geometry)
    for item in ranked:
        item.verified = True
        _note_detour(item)
    chosen = ranked[0] if ranked else None
    alts = ranked[1:4]
    return PlanOutcome(
        candidate=chosen,
        alternatives=alts,
        route=route,
        places_cache=raw,
        provider="fixture",
        spoken=_spoken(constraints, chosen, False, alts),
    )


async def execute_plan(
    settings,
    constraints: MissionConstraints,
    skip_ids: set[str],
    reuse_route: RouteSnapshot | None = None,
    reuse_places: list[PlaceCandidate] | None = None,
) -> PlanOutcome:
    mode = (settings.geo_mode or "fixture").lower()
    if mode != "live":
        return fixture_plan(constraints, skip_ids)
    try:
        return await live_plan(settings, constraints, skip_ids, reuse_route, reuse_places)
    except ValueError as exc:
        reason = str(exc)
        route = reuse_route or corridor_snapshot(constraints.avoid_tolls)
        if reason == "destination_not_found":
            spoken = "I could not find that destination on the map, so I did not change the route."
        elif reason == "origin_not_found":
            spoken = "I could not find that starting point on the map, so I did not change the route."
        else:
            spoken = format_none()
        return PlanOutcome(
            candidate=None,
            alternatives=[],
            route=route,
            places_cache=reuse_places or [],
            provider="nominatim",
            spoken=spoken,
        )
    except Exception as exc:
        logger.info("live plan transport failed: %s", exc)
        fallback = fixture_plan(constraints, skip_ids)
        fallback.fallback_used = True
        fallback.provider = "fixture-fallback"
        fallback.spoken = _spoken(constraints, fallback.candidate, True)
        fallback.transport_failed = True
        return fallback


async def boot_corridor(settings) -> RouteSnapshot:
    dummy = MissionConstraints(category="coffee")
    if (settings.geo_mode or "fixture").lower() != "live":
        return corridor_snapshot(False)
    try:
        origin_q, dest_q, ends = await resolve_endpoints(settings, dummy)
        router = OsrmRouter(settings.osrm_url)
        routed = await router.baseline(
            (ends.origin_lat, ends.origin_lng),
            (ends.dest_lat, ends.dest_lng),
            avoid_tolls=False,
            origin_name=ends.origin_name,
            dest_name=ends.destination_name,
            origin_query=origin_q,
            dest_query=dest_q,
        )
        return routed or corridor_snapshot(False)
    except Exception as exc:
        logger.info("boot corridor fell back to fixture: %s", exc)
        return corridor_snapshot(False)
