from pathlib import Path

import pytest

from mid_drive.evidence import collect
from mid_drive.speech import SEARCH_HOLD, format_inquire, spoken_place
from mid_drive.models import MissionConstraints, PlaceCandidate


@pytest.mark.asyncio
async def test_official_evidence_three_rounds(tmp_path: Path) -> None:
    payload = await collect(tmp_path)
    assert payload["rounds"] == 3
    assert payload["stale_admissions"] == 0
    assert payload["stale_rejects"] == 3
    for row in payload["official"]:
        assert row["spoken_shop"] == "Starbucks"
        assert row["stale_decision"] == "stale_rejected"
    for row in payload["judged_voice"]:
        assert row["final_shop"] == "Starbucks"
        assert row["parking"] is True
        assert row["avoid_tolls"] is True


def test_inflight_status_tells_the_driver_to_revise() -> None:
    spoken = format_inquire(
        "status",
        MissionConstraints(category="coffee", parking_required=True),
        None,
        [],
        None,
        search_inflight=True,
        search_version=2,
        search_delay_s=8,
    )
    assert "Still searching" in spoken
    assert "eight second" in spoken
    assert "drop the old result" in spoken
    assert SEARCH_HOLD.startswith("I'll keep listening")


def test_spoken_place_shortens_for_the_ear() -> None:
    assert spoken_place("Blue Tokai Coffee Roasters") == "Blue Tokai"
    chai = PlaceCandidate(id="c", name="Chai Point", area="NH 48", category="coffee")
    line = format_inquire("where", MissionConstraints(category="coffee"), chai, [], None)
    assert line == "Chai Point is in NH 48."
