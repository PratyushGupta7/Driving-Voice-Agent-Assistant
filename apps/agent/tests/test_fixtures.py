from mid_drive.fixtures_data import format_candidate, pick_candidate, pick_candidates
from mid_drive.models import MissionConstraints


def test_parking_required_skips_unknown_and_no() -> None:
    chosen = pick_candidate(MissionConstraints(category="coffee", parking_required=True))
    assert chosen is not None
    assert chosen.parking == "yes"
    assert chosen.id == "blue-tokai-cyber-hub"


def test_another_coffee_with_parking() -> None:
    options = pick_candidates(
        MissionConstraints(category="coffee", parking_required=True),
        skip_ids={"blue-tokai-cyber-hub"},
    )
    assert options[0].id == "starbucks-cyber-hub"


def test_spoken_wording_is_honest() -> None:
    constraints = MissionConstraints(category="coffee", parking_required=True, avoid_tolls=True)
    chosen = pick_candidate(constraints)
    assert chosen is not None
    spoken = format_candidate(constraints, chosen)
    assert "reports a parking lot" in spoken
    assert "requested a toll-avoiding route" in spoken
    assert "available" not in spoken
    assert "toll-free" not in spoken


def test_detour_filter() -> None:
    chosen = pick_candidate(MissionConstraints(category="coffee", maximum_detour_minutes=3))
    assert chosen is None or chosen.detour_minutes <= 3
    tight = pick_candidate(MissionConstraints(category="coffee", parking_required=True, maximum_detour_minutes=3))
    assert tight is None


def test_juice_demo_ranks() -> None:
    first = pick_candidate(MissionConstraints(category="juice"))
    assert first is not None and first.id == "fresh-juice-nh48"
    parked = pick_candidate(MissionConstraints(category="juice", parking_required=True))
    assert parked is not None and parked.id == "raw-pressery-cyber-hub"
    tolls = pick_candidate(
        MissionConstraints(category="juice", parking_required=True, avoid_tolls=True)
    )
    assert tolls is not None and tolls.id == "the-juicery-cyber-hub"
    other = pick_candidates(
        MissionConstraints(category="juice", parking_required=True, avoid_tolls=True),
        skip_ids={"the-juicery-cyber-hub"},
    )
    assert other[0].id == "raw-pressery-cyber-hub"


def test_candidates_have_coordinates() -> None:
    chosen = pick_candidate(MissionConstraints(category="coffee"))
    assert chosen is not None
    assert chosen.lat and chosen.lng
