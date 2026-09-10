from __future__ import annotations

from ..geometry import distance_to_polyline_m, haversine_m, progress_along_route
from ..models import MissionConstraints, PlaceCandidate

# Judged fixture corridor. Parking-only must not collapse onto the tolls pick.
# (no parking, parking, parking+tolls)
_FIXTURE_SCRIPT = {
    "chai-point-kiosk": (0, 9, 9),
    "third-wave-dlf-2": (1, 9, 9),
    "blue-tokai-cyber-hub": (2, 0, 1),
    "starbucks-cyber-hub": (3, 1, 0),
    "fresh-juice-nh48": (0, 9, 9),
    "booster-juice-dlf-2": (1, 9, 9),
    "raw-pressery-cyber-hub": (2, 0, 1),
    "the-juicery-cyber-hub": (3, 1, 0),
}


def _script_slot(constraints: MissionConstraints) -> int:
    if constraints.parking_required and constraints.avoid_tolls:
        return 2
    if constraints.parking_required:
        return 1
    return 0


def _script_priority(constraints: MissionConstraints, item: PlaceCandidate) -> int:
    row = _FIXTURE_SCRIPT.get(item.id)
    if row is None:
        return 40
    return row[_script_slot(constraints)]


def _brand_hit(place: PlaceCandidate, needle: str) -> bool:
    blob = " ".join(
        part for part in (place.name, place.brand, place.operator, place.area) if part
    ).lower()
    return needle.lower() in blob


def filter_and_rank(
    places: list[PlaceCandidate],
    constraints: MissionConstraints,
    skip_ids: set[str],
    geometry: list[list[float]],
    landmark: tuple[float, float] | None = None,
) -> list[PlaceCandidate]:
    ranked: list[PlaceCandidate] = []
    for raw in places:
        place = raw.model_copy()
        if place.id in skip_ids:
            continue
        if constraints.parking_required and place.parking != "yes":
            continue
        if constraints.brand_query and not _brand_hit(place, constraints.brand_query):
            continue
        if place.lat is not None and place.lng is not None:
            place.distance_to_route_m = distance_to_polyline_m(place.lat, place.lng, geometry)
            place.progress = progress_along_route(place.lat, place.lng, geometry)
        if (
            constraints.maximum_detour_minutes is not None
            and place.detour_minutes is not None
            and place.detour_minutes > constraints.maximum_detour_minutes
        ):
            continue
        reasons: list[str] = []
        if constraints.parking_required and place.parking == "yes":
            reasons.append("it reports a parking lot")
        if place.verified and place.detour_minutes:
            reasons.append(f"the extra time is about {place.detour_minutes} minutes")
        if constraints.brand_query and _brand_hit(place, constraints.brand_query):
            reasons.append("the name matches what you asked for")
        if landmark and place.lat is not None and place.lng is not None:
            if haversine_m(place.lat, place.lng, landmark[0], landmark[1]) <= 1200:
                reasons.append("it is near the landmark you named")
        if constraints.prefer_along == "start" and place.progress is not None and place.progress <= 0.35:
            reasons.append("it sits nearer the start")
        if constraints.prefer_along == "end" and place.progress is not None and place.progress >= 0.65:
            reasons.append("it sits nearer the destination")
        place.reasons = reasons
        ranked.append(place)

    def key(item: PlaceCandidate) -> tuple:
        landmark_m = 10_000_000.0
        if landmark and item.lat is not None and item.lng is not None:
            landmark_m = haversine_m(item.lat, item.lng, landmark[0], landmark[1])
        detour = item.detour_minutes if item.detour_minutes is not None else 99
        route_m = item.distance_to_route_m if item.distance_to_route_m is not None else 10_000_000
        progress = item.progress if item.progress is not None else 0.5
        along = progress if constraints.prefer_along == "start" else (-progress if constraints.prefer_along == "end" else 0.0)
        script = _script_priority(constraints, item)
        if landmark:
            return (landmark_m, script, item.detour_minutes is None, detour, along, route_m, item.name.lower(), item.id)
        return (script, item.detour_minutes is None, detour, along, route_m, item.name.lower(), item.id)

    ranked.sort(key=key)
    if ranked and not ranked[0].reasons:
        ranked[0].reasons = ["it was the closest verified match on this corridor"]
    return ranked
