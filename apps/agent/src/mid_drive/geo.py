from __future__ import annotations

from .fixtures_data import format_candidate, format_none
from .models import MissionConstraints, PlaceCandidate, RouteSnapshot
from .providers.overpass import parking_from_tags as _parking_from_tags
from .providers.plan import execute_plan

__all__ = ["resolve_place", "spoken_for", "_parking_from_tags"]


async def resolve_place(
    settings,
    constraints: MissionConstraints,
    skip_ids: set[str],
) -> tuple[PlaceCandidate | None, RouteSnapshot, str, bool]:
    """Facade over the provider plan. Returns candidate, route, provider, fallback_used."""
    outcome = await execute_plan(settings, constraints, skip_ids)
    return outcome.candidate, outcome.route, outcome.provider, outcome.fallback_used


def spoken_for(
    constraints: MissionConstraints,
    candidate: PlaceCandidate | None,
    fallback_used: bool,
) -> str:
    if candidate is None:
        text = format_none()
    else:
        text = format_candidate(constraints, candidate)
    if fallback_used:
        return "Live maps did not answer in time, so I used the saved corridor. " + text
    return text
