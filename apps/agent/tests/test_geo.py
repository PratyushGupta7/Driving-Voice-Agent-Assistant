import pytest

from mid_drive.fixtures_data import corridor_snapshot
from mid_drive.geo import _parking_from_tags
from mid_drive.orchestrator import fixture_delay_seconds
from mid_drive.providers.geocode import _CACHE, GeocodeTransportError, geocode


def test_corridor_is_real_osrm_shape() -> None:
    route = corridor_snapshot()
    assert len(route.geometry) > 10
    assert route.duration_s and route.duration_s > 1000
    assert route.geometry[0][0] < route.geometry[-1][0]


def test_parking_tags() -> None:
    assert _parking_from_tags({"parking": "yes"}) == "yes"
    assert _parking_from_tags({"parking": "no"}) == "no"
    assert _parking_from_tags({}) == "unknown"
    assert _parking_from_tags({"amenity": "parking"}) == "yes"


def test_delay_only_in_fixture_mode() -> None:
    assert fixture_delay_seconds(2, "fixture") == 8.0
    assert fixture_delay_seconds(2, "live") == 0.0
    assert fixture_delay_seconds(1, "fixture") == 0.0
    assert fixture_delay_seconds(3, "fixture") == 0.0


@pytest.mark.asyncio
async def test_geocode_does_not_cache_transport_failure(monkeypatch) -> None:
    from mid_drive.providers import geocode as geocode_mod

    _CACHE.clear()

    async def boom(*_args, **_kwargs):
        raise RuntimeError("timeout")

    monkeypatch.setattr(geocode_mod, "request_with_retry", boom)
    with pytest.raises(GeocodeTransportError):
        await geocode("https://example.test", "Cyber Hub")
    assert "cyber hub" not in _CACHE
