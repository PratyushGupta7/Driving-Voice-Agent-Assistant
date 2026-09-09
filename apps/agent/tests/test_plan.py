from types import SimpleNamespace

import pytest

from mid_drive.fixtures_data import corridor_snapshot, format_candidate, format_none
from mid_drive.models import MissionConstraints, PlaceCandidate, needs_new_places, needs_new_route
from mid_drive.providers.osrm import route_params, settings_key
from mid_drive.providers.plan import PlanOutcome, execute_plan, fixture_plan
from mid_drive.providers.rank import filter_and_rank


def _place(**kwargs) -> PlaceCandidate:
    base = dict(id="a", name="Alpha Cafe", area="Cyber Hub", category="coffee", parking="unknown")
    base.update(kwargs)
    return PlaceCandidate(**base)  # type: ignore[arg-type]


def test_route_settings_identical_for_baseline_and_via() -> None:
    assert route_params(True) == route_params(True)
    assert route_params(False) == route_params(False)
    assert route_params(True)["exclude"] == "toll"
    assert "exclude" not in route_params(False)
    assert settings_key(True) == "driving|exclude=toll"
    assert settings_key(False) == "driving"


def test_parking_unknown_rejected_when_required() -> None:
    places = [
        _place(id="u", name="Unknown Cup", parking="unknown", detour_minutes=2),
        _place(id="p", name="Parked Cup", parking="yes", detour_minutes=6),
    ]
    ranked = filter_and_rank(
        places,
        MissionConstraints(category="coffee", parking_required=True),
        set(),
        corridor_snapshot().geometry,
    )
    assert [item.id for item in ranked] == ["p"]


def test_ranking_is_stable() -> None:
    places = [
        _place(id="b", name="Blue", parking="yes", detour_minutes=7, lat=28.5, lng=77.1),
        _place(id="s", name="Starbucks", parking="yes", detour_minutes=6, lat=28.5, lng=77.1),
        _place(id="s2", name="Starbucks", parking="yes", detour_minutes=6, lat=28.5, lng=77.1),
    ]
    first = [item.id for item in filter_and_rank(places, MissionConstraints(category="coffee"), set(), [])]
    second = [item.id for item in filter_and_rank(list(reversed(places)), MissionConstraints(category="coffee"), set(), [])]
    assert first == second == ["s", "s2", "b"]


def test_landmark_outranks_detour() -> None:
    places = [
        _place(id="far", name="Far", parking="yes", detour_minutes=3, lat=28.63, lng=77.22),
        _place(id="near", name="Near Hub", parking="yes", detour_minutes=8, lat=28.4955, lng=77.0888),
    ]
    ranked = filter_and_rank(
        places,
        MissionConstraints(category="coffee", landmark_query="Cyber Hub"),
        set(),
        corridor_snapshot().geometry,
        landmark=(28.4947, 77.0883),
    )
    assert ranked[0].id == "near"


def test_no_spoken_detour_without_via() -> None:
    unverified = _place(name="Ghost Cafe", detour_minutes=9, verified=False)
    spoken = format_candidate(MissionConstraints(category="coffee"), unverified)
    assert "extra time" not in spoken
    verified = unverified.model_copy(update={"verified": True})
    assert "extra time" in format_candidate(MissionConstraints(category="coffee"), verified)


def test_fixture_plan_ranks_by_detour() -> None:
    v1 = fixture_plan(MissionConstraints(category="coffee"), set())
    assert v1.candidate is not None
    assert v1.candidate.id == "chai-point-kiosk"
    parked = fixture_plan(MissionConstraints(category="coffee", parking_required=True), set())
    assert parked.candidate is not None
    assert parked.candidate.parking == "yes"
    assert parked.candidate.id == "blue-tokai-cyber-hub"
    v3 = fixture_plan(
        MissionConstraints(category="coffee", parking_required=True, avoid_tolls=True),
        set(),
    )
    assert v3.candidate is not None
    assert v3.candidate.id == "starbucks-cyber-hub"
    nxt = fixture_plan(
        MissionConstraints(category="coffee", parking_required=True, avoid_tolls=True),
        {"starbucks-cyber-hub"},
    )
    assert nxt.candidate is not None
    assert nxt.candidate.id == "blue-tokai-cyber-hub"


def test_dependency_table() -> None:
    coffee = MissionConstraints(category="coffee")
    parked = MissionConstraints(category="coffee", parking_required=True)
    tolls = MissionConstraints(category="coffee", parking_required=True, avoid_tolls=True)
    fuel = MissionConstraints(category="fuel", parking_required=True, avoid_tolls=True)
    dest = MissionConstraints(category="coffee", destination_query="India Gate")
    assert needs_new_route(coffee, parked) is False
    assert needs_new_places(coffee, parked) is False
    assert needs_new_route(parked, tolls) is True
    assert needs_new_places(coffee, fuel) is True
    assert needs_new_route(coffee, dest) is True


@pytest.mark.asyncio
async def test_live_empty_does_not_substitute_fixture(monkeypatch) -> None:
    from mid_drive.providers import plan as plan_mod

    async def fake_live(*_args, **_kwargs) -> PlanOutcome:
        return PlanOutcome(
            candidate=None,
            alternatives=[],
            route=corridor_snapshot(),
            provider="overpass+osrm",
            spoken=format_none(),
        )

    monkeypatch.setattr(plan_mod, "live_plan", fake_live)
    settings = SimpleNamespace(geo_mode="live")
    outcome = await execute_plan(settings, MissionConstraints(category="coffee"), set())
    assert outcome.candidate is None
    assert outcome.fallback_used is False
    assert "Blue Tokai" not in outcome.spoken
    assert "saved corridor" not in outcome.spoken


@pytest.mark.asyncio
async def test_live_transport_failure_speaks_fallback(monkeypatch) -> None:
    from mid_drive.providers import plan as plan_mod

    async def boom(*_args, **_kwargs):
        raise RuntimeError("osrm_baseline_failed")

    monkeypatch.setattr(plan_mod, "live_plan", boom)
    settings = SimpleNamespace(geo_mode="live")
    outcome = await execute_plan(settings, MissionConstraints(category="coffee"), set())
    assert outcome.fallback_used is True
    assert outcome.transport_failed is True
    assert "saved corridor" in outcome.spoken
    assert outcome.candidate is not None
