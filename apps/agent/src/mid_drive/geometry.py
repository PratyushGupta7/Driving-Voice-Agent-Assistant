from __future__ import annotations

import math

from .models import RouteSnapshot


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1, math.sqrt(a)))


def _xy(lat: float, lng: float, lat0: float) -> tuple[float, float]:
    return math.radians(lng) * math.cos(math.radians(lat0)), math.radians(lat)


def _closest_on_segment(
    lat: float,
    lng: float,
    lat_a: float,
    lng_a: float,
    lat_b: float,
    lng_b: float,
) -> tuple[float, float, float]:
    """Return (lat, lng, t in 0..1) of the closest point on segment AB."""
    lat0 = (lat_a + lat_b) / 2 or lat
    ax, ay = _xy(lat_a, lng_a, lat0)
    bx, by = _xy(lat_b, lng_b, lat0)
    px, py = _xy(lat, lng, lat0)
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom <= 1e-18:
        return lat_a, lng_a, 0.0
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    return lat_a + t * (lat_b - lat_a), lng_a + t * (lng_b - lng_a), t


def distance_to_polyline_m(lat: float, lng: float, geometry: list[list[float]]) -> float | None:
    if not geometry:
        return None
    best: float | None = None
    if len(geometry) == 1:
        return haversine_m(lat, lng, geometry[0][1], geometry[0][0])
    for index in range(len(geometry) - 1):
        lng_a, lat_a = geometry[index]
        lng_b, lat_b = geometry[index + 1]
        plat, plng, _ = _closest_on_segment(lat, lng, lat_a, lng_a, lat_b, lng_b)
        dist = haversine_m(lat, lng, plat, plng)
        best = dist if best is None else min(best, dist)
    return best


def progress_along_route(lat: float, lng: float, geometry: list[list[float]]) -> float | None:
    if len(geometry) < 2:
        return None
    lengths: list[float] = []
    total = 0.0
    for index in range(len(geometry) - 1):
        lng_a, lat_a = geometry[index]
        lng_b, lat_b = geometry[index + 1]
        seg = haversine_m(lat_a, lng_a, lat_b, lng_b)
        lengths.append(seg)
        total += seg
    if total <= 1:
        return None
    best_dist = None
    best_along = 0.0
    walked = 0.0
    for index in range(len(geometry) - 1):
        lng_a, lat_a = geometry[index]
        lng_b, lat_b = geometry[index + 1]
        plat, plng, t = _closest_on_segment(lat, lng, lat_a, lng_a, lat_b, lng_b)
        dist = haversine_m(lat, lng, plat, plng)
        along = walked + t * lengths[index]
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_along = along
        walked += lengths[index]
    return max(0.0, min(1.0, best_along / total))


def enrich_route(route: RouteSnapshot) -> RouteSnapshot:
    if route.duration_s:
        route.eta_minutes = max(1, round(route.duration_s / 60))
    if route.distance_m:
        route.distance_km = round(route.distance_m / 1000, 1)
    bits: list[str] = []
    if route.eta_minutes:
        bits.append(f"{route.eta_minutes} min")
    if route.distance_km:
        bits.append(f"{route.distance_km} km")
    if route.avoid_tolls:
        bits.append("toll-avoiding requested")
    route.summary = " · ".join(bits)
    return route
