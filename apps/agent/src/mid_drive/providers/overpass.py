from __future__ import annotations

from typing import Any

from .client import request_with_retry
from ..geometry import haversine_m
from ..models import PlaceCandidate

AMENITY = {
    "coffee": (("amenity", "cafe"), ("shop", "coffee")),
    "fuel": (("amenity", "fuel"),),
    "pharmacy": (("amenity", "pharmacy"),),
    "juice": (("shop", "juice"), ("shop", "beverages")),
}


def parking_from_tags(tags: dict[str, Any]) -> str:
    raw = str(tags.get("parking") or tags.get("parking:lane") or "").lower()
    if raw in {"yes", "multi-storey", "surface", "underground", "street_side"}:
        return "yes"
    if raw in {"no", "none"}:
        return "no"
    if tags.get("amenity") == "parking":
        return "yes"
    return "unknown"


def sample_points(geometry: list[list[float]], count: int = 16) -> list[tuple[float, float]]:
    if not geometry:
        return []
    if len(geometry) <= count:
        return [(lat, lng) for lng, lat in geometry]
    step = max(1, (len(geometry) - 1) // (count - 1))
    points = [(geometry[i][1], geometry[i][0]) for i in range(0, len(geometry), step)]
    last = (geometry[-1][1], geometry[-1][0])
    if points[-1] != last:
        points.append(last)
    return points[: count + 1]


def _coord(element: dict[str, Any]) -> tuple[float, float] | None:
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center") or {}
    if "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None


def _around_clause(geometry: list[list[float]], radius_m: int = 500) -> str:
    samples = sample_points(geometry, 16)
    coords = ",".join(f"{lat:.5f},{lng:.5f}" for lat, lng in samples)
    return f"(around:{radius_m},{coords})"


class OverpassPlaces:
    def __init__(self, url: str) -> None:
        self.url = url

    async def along_route(
        self,
        category: str,
        geometry: list[list[float]],
    ) -> list[PlaceCandidate]:
        pairs = AMENITY[category]
        around = _around_clause(geometry)
        clauses: list[str] = []
        for key, value in pairs:
            clauses.append(f'node["{key}"="{value}"]{around};')
            clauses.append(f'way["{key}"="{value}"]{around};')
        clauses.append(f'node["amenity"="parking"]{around};')
        query = f"[out:json][timeout:15];({''.join(clauses)});out center 80;"
        response = await request_with_retry(
            "POST",
            self.url,
            timeout=16.0,
            content=query.encode("utf-8"),
        )
        payload = response.json()

        parking_pts: list[tuple[float, float]] = []
        raw_places: list[tuple[dict[str, Any], tuple[float, float]]] = []
        for element in payload.get("elements", []):
            tags = element.get("tags") or {}
            coord = _coord(element)
            if coord is None:
                continue
            if tags.get("amenity") == "parking":
                parking_pts.append(coord)
                continue
            if tags.get("name"):
                raw_places.append((element, coord))

        places: list[PlaceCandidate] = []
        seen: set[str] = set()
        for element, coord in raw_places:
            tags = element.get("tags") or {}
            osm_id = f"osm-{element.get('type', 'node')}-{element['id']}"
            if osm_id in seen:
                continue
            seen.add(osm_id)
            parking = parking_from_tags(tags)
            if parking == "unknown" and any(
                haversine_m(coord[0], coord[1], plat, plng) <= 80 for plat, plng in parking_pts
            ):
                parking = "yes"
            area = (
                tags.get("addr:suburb")
                or tags.get("addr:city")
                or tags.get("addr:district")
                or "along the corridor"
            )
            hours = tags.get("opening_hours")
            places.append(
                PlaceCandidate(
                    id=osm_id,
                    name=str(tags["name"]),
                    area=area,
                    category=category,  # type: ignore[arg-type]
                    parking=parking,  # type: ignore[arg-type]
                    lat=coord[0],
                    lng=coord[1],
                    provenance="overpass",
                    brand=tags.get("brand"),
                    operator=tags.get("operator"),
                    opening_hours=str(hours) if hours else None,
                )
            )
        return places
