from __future__ import annotations

from .client import request_with_retry
from ..geometry import enrich_route
from ..models import PlaceCandidate, RouteSnapshot


def route_params(avoid_tolls: bool, *, overview: str = "full") -> dict[str, str]:
    """Identical settings for baseline and via so comparisons are valid."""
    params = {"overview": overview, "geometries": "geojson", "alternatives": "false"}
    if avoid_tolls:
        params["exclude"] = "toll"
    return params


def settings_key(avoid_tolls: bool) -> str:
    return "driving|exclude=toll" if avoid_tolls else "driving"


class OsrmRouter:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def route(
        self,
        points: list[tuple[float, float]],
        *,
        avoid_tolls: bool,
        origin_name: str,
        dest_name: str,
        origin_query: str = "",
        dest_query: str = "",
    ) -> RouteSnapshot | None:
        if len(points) < 2:
            return None
        coords = ";".join(f"{lng},{lat}" for lat, lng in points)
        params = route_params(avoid_tolls, overview="full")
        url = f"{self.base_url}/route/v1/driving/{coords}"
        try:
            response = await request_with_retry("GET", url, timeout=8.0, params=params)
            data = response.json()
            raw = data["routes"][0]
            geometry = raw["geometry"]["coordinates"]
            origin = points[0]
            dest = points[-1]
            snap = RouteSnapshot(
                origin_name=origin_name,
                destination_name=dest_name,
                origin_lat=origin[0],
                origin_lng=origin[1],
                dest_lat=dest[0],
                dest_lng=dest[1],
                geometry=geometry,
                via_geometry=geometry if len(points) > 2 else [],
                duration_s=int(raw.get("duration") or 0),
                distance_m=int(raw.get("distance") or 0),
                avoid_tolls=avoid_tolls,
                provider="osrm",
                origin_query=origin_query,
                dest_query=dest_query,
                settings_hash=settings_key(avoid_tolls),
            )
            return enrich_route(snap)
        except Exception:
            return None

    async def baseline(
        self,
        origin: tuple[float, float],
        dest: tuple[float, float],
        *,
        avoid_tolls: bool,
        origin_name: str,
        dest_name: str,
        origin_query: str,
        dest_query: str,
    ) -> RouteSnapshot | None:
        return await self.route(
            [origin, dest],
            avoid_tolls=avoid_tolls,
            origin_name=origin_name,
            dest_name=dest_name,
            origin_query=origin_query,
            dest_query=dest_query,
        )

    async def via(
        self,
        baseline: RouteSnapshot,
        place: PlaceCandidate,
    ) -> RouteSnapshot | None:
        if place.lat is None or place.lng is None:
            return None
        routed = await self.route(
            [
                (baseline.origin_lat, baseline.origin_lng),
                (place.lat, place.lng),
                (baseline.dest_lat, baseline.dest_lng),
            ],
            avoid_tolls=baseline.avoid_tolls,
            origin_name=baseline.origin_name,
            dest_name=baseline.destination_name,
            origin_query=baseline.origin_query,
            dest_query=baseline.dest_query,
        )
        if routed is None:
            return None
        if routed.settings_hash != baseline.settings_hash:
            return None
        return routed
