from mid_drive.geometry import distance_to_polyline_m, haversine_m, progress_along_route
from mid_drive.models import MissionConstraints, MissionPatch, PlaceCandidate, SessionPrefs
from mid_drive.providers.rank import filter_and_rank
from mid_drive.reducer import reduce_mission
from mid_drive.revision import parse_turn
from mid_drive.session_actor import SessionActor
from mid_drive.speech import format_candidate, format_inquire


def test_select_and_inquire_parse() -> None:
    current = MissionConstraints(category="coffee")
    assert parse_turn("the second one", current).operation == "select"
    assert parse_turn("the second one", current).select_index == 2
    assert parse_turn("go with Starbucks", current).select_name == "Starbucks"
    assert parse_turn("why this one", current).inquire_kind == "why"
    assert parse_turn("how much extra time", current).inquire_kind == "eta"
    assert parse_turn("does it have parking", current).inquire_kind == "parking"
    assert parse_turn("what did you find", current).inquire_kind == "why"
    assert parse_turn("Find me a coffee shop near my route", None).brand_query is None


def test_brand_and_prefer_along() -> None:
    patch = parse_turn("Find coffee called Blue Tokai", None)
    assert patch.operation == "create"
    assert patch.category == "coffee"
    assert patch.brand_query == "Blue Tokai"
    current = MissionConstraints(category="coffee")
    start = parse_turn("nearer the start", current)
    assert start.prefer_along == "start"
    assert parse_turn("Find a coffee shop near my route", None).brand_query is None
    assert parse_turn("Find a coffee shop near my route", None).landmark_query is None


def test_session_pref_applies_on_next_create() -> None:
    prefs = SessionPrefs(parking_required=True)
    result = reduce_mission(None, MissionPatch(operation="create", category="fuel"), prefs)
    assert result.constraints is not None
    assert result.constraints.parking_required is True
    assert "parking" in (result.acknowledgement or "").lower()


def test_select_offered_switches_without_new_search() -> None:
    actor = SessionActor("s1")
    actor.commit_revision(MissionConstraints(category="coffee"), "active", True)
    first = PlaceCandidate(id="a", name="Alpha", area="Hub", category="coffee")
    second = PlaceCandidate(id="b", name="Bravo", area="Hub", category="coffee")
    actor.accept_bundle(first, [second])
    chosen = actor.select_offered(index=2)
    assert chosen is not None
    assert chosen.id == "b"
    assert actor.selected is not None and actor.selected.id == "b"
    assert actor.alternatives[0].id == "a"


def test_inquire_does_not_invent_occupancy() -> None:
    selected = PlaceCandidate(id="a", name="Alpha", area="Hub", category="coffee", parking="yes")
    spoken = format_inquire("parking", MissionConstraints(category="coffee"), selected, [], None)
    assert "reports a parking lot" in spoken
    assert "available" not in spoken


def test_parking_speech_covers_both_options() -> None:
    selected = PlaceCandidate(id="s", name="Starbucks", area="Hub", category="coffee", parking="yes")
    other = PlaceCandidate(id="b", name="Blue Tokai", area="Hub", category="coffee", parking="yes")
    spoken = format_candidate(
        MissionConstraints(category="coffee", parking_required=True),
        selected,
        [other],
    )
    assert "This place reports a parking lot" in spoken
    assert "Blue Tokai" in spoken
    assert "lot too" in spoken
    inquire = format_inquire(
        "parking",
        MissionConstraints(category="coffee", parking_required=True),
        selected,
        [other],
        None,
    )
    assert "Starbucks reports a parking lot" in inquire
    assert "Blue Tokai reports a lot as well" in inquire


def test_brand_rank_filters() -> None:
    places = [
        PlaceCandidate(id="a", name="Other Cup", area="Hub", category="coffee", parking="yes", detour_minutes=3),
        PlaceCandidate(id="b", name="Blue Tokai Coffee Roasters", area="Hub", category="coffee", parking="yes", detour_minutes=7),
    ]
    ranked = filter_and_rank(
        places,
        MissionConstraints(category="coffee", brand_query="Tokai"),
        set(),
        [],
    )
    assert [item.id for item in ranked] == ["b"]


def test_segment_distance_beats_vertex_only() -> None:
    geometry = [[77.0, 28.0], [77.02, 28.0]]
    lat, lng = 28.001, 77.01
    projected = distance_to_polyline_m(lat, lng, geometry)
    vertex = min(haversine_m(lat, lng, 28.0, 77.0), haversine_m(lat, lng, 28.0, 77.02))
    assert projected is not None
    assert projected < vertex
    progress = progress_along_route(lat, lng, geometry)
    assert progress is not None
    assert 0.3 < progress < 0.7


def test_parking_hold_another_one_keeps_lot_alts() -> None:
    actor = SessionActor("s1")
    actor.commit_revision(MissionConstraints(category="coffee", parking_required=True), "active", True)
    chai = PlaceCandidate(id="c", name="Chai Point", area="Hub", category="coffee", parking="no")
    third = PlaceCandidate(id="t", name="Third Wave", area="Hub", category="coffee", parking="unknown")
    blue = PlaceCandidate(id="b", name="Blue Tokai", area="Hub", category="coffee", parking="yes")
    actor.accept_bundle(chai, [third, blue])
    actor.reject_selected()
    assert "c" in actor.rejected_ids
    assert "t" in actor.rejected_ids
    assert "b" not in actor.rejected_ids


def test_another_one_after_parking_pick_skips_shown_lots() -> None:
    actor = SessionActor("s1")
    actor.commit_revision(MissionConstraints(category="coffee", parking_required=True), "active", True)
    blue = PlaceCandidate(id="b", name="Blue Tokai", area="Hub", category="coffee", parking="yes")
    star = PlaceCandidate(id="s", name="Starbucks", area="Hub", category="coffee", parking="yes")
    actor.accept_bundle(blue, [star])
    actor.reject_selected()
    assert "b" in actor.rejected_ids
    assert "s" in actor.rejected_ids


def test_spoken_mentions_alternative() -> None:
    chosen = PlaceCandidate(id="a", name="Starbucks", area="Cyber Hub", category="coffee", verified=True, detour_minutes=6)
    alt = PlaceCandidate(id="b", name="Blue Tokai Coffee Roasters", area="Cyber Hub", category="coffee")
    spoken = format_candidate(MissionConstraints(category="coffee"), chosen, [alt])
    assert "Starbucks" in spoken
    assert "Blue Tokai" in spoken
    assert "available" not in spoken
