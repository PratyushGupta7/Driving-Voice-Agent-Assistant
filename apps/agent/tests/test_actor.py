from mid_drive.models import MissionConstraints, OutputGate
from mid_drive.session_actor import SessionActor


def _coffee(**kwargs: object) -> MissionConstraints:
    return MissionConstraints(category="coffee", **kwargs)  # type: ignore[arg-type]


def test_protected_greeting_does_not_cut_speech() -> None:
    actor = SessionActor("s1")
    actor.protect_speech = True
    actor.current_speech_handle = type("H", (), {"done": lambda self: False, "interrupt": lambda self, force=True: (_ for _ in ()).throw(AssertionError("must not interrupt"))})()
    epoch = actor.output_epoch
    assert actor.on_user_speaking() is None
    assert actor.output_epoch == epoch


def test_echo_holdoff_ignores_onset() -> None:
    actor = SessionActor("s1")
    actor.mark_speech_started()
    actor.current_speech_handle = type("H", (), {"done": lambda self: False, "interrupt": lambda self, force=True: (_ for _ in ()).throw(AssertionError("must not interrupt"))})()
    epoch = actor.output_epoch
    assert actor.on_user_speaking() is None
    assert actor.output_epoch == epoch


def test_vad_advances_epoch_not_version() -> None:
    actor = SessionActor("s1")
    actor.commit_revision(_coffee(), "active", True)
    assert actor.mission_version == 1
    epoch = actor.output_epoch
    actor.on_user_speaking()
    assert actor.output_epoch == epoch + 1
    assert actor.mission_version == 1
    assert actor.output_gate is OutputGate.CLOSED_FOR_INPUT


def test_material_revision_increments_version() -> None:
    actor = SessionActor("s1")
    actor.commit_revision(_coffee(), "active", True)
    actor.on_user_speaking()
    actor.commit_revision(_coffee(parking_required=True), "active", True)
    assert actor.mission_version == 2
    assert actor.output_gate is OutputGate.OPEN


def test_epoch_never_decrements() -> None:
    actor = SessionActor("s1")
    actor.on_user_speaking()
    actor.on_user_speaking()
    actor.on_user_speaking()
    assert actor.output_epoch == 3
    actor.commit_revision(_coffee(), "active", True)
    assert actor.output_epoch == 3


def test_consumed_token_cannot_commit_but_can_speak() -> None:
    actor = SessionActor("s1")
    actor.commit_revision(_coffee(), "active", True)
    token = actor.issue_token("place_search")
    assert actor.may_commit(token)
    actor.consume_request(token)
    assert actor.may_commit(token) is False
    assert actor.may_emit(token) is True


def test_old_token_cannot_emit_after_barrier() -> None:
    actor = SessionActor("s1")
    actor.commit_revision(_coffee(), "active", True)
    token = actor.issue_token("place_search")
    assert actor.may_emit(token)
    actor.on_user_speaking()
    assert actor.may_commit(token) is False
    assert actor.may_emit(token) is False


def test_selected_clears_on_material_revision() -> None:
    from mid_drive.models import PlaceCandidate

    actor = SessionActor("s1")
    actor.commit_revision(_coffee(), "active", True)
    actor.accept_candidate(
        PlaceCandidate(id="a", name="Blue Tokai Coffee Roasters", area="Cyber Hub", category="coffee")
    )
    actor.commit_revision(_coffee(parking_required=True), "active", True)
    assert actor.selected is None


def test_keep_places_on_parking_revision() -> None:
    from mid_drive.models import PlaceCandidate

    actor = SessionActor("s1")
    actor.commit_revision(_coffee(), "active", True)
    actor.accept_candidate(
        PlaceCandidate(id="c", name="Chai Point", area="NH 48", category="coffee", parking="no")
    )
    actor.commit_revision(_coffee(parking_required=True), "active", True, keep_places=True)
    assert actor.selected is not None
    assert actor.selected.name == "Chai Point"
    assert actor.mission_version == 2


def test_geo_cache_is_keyed() -> None:
    from mid_drive.fixtures_data import corridor_snapshot
    from mid_drive.models import PlaceCandidate

    actor = SessionActor("s1")
    actor.commit_revision(_coffee(), "active", True)
    place = PlaceCandidate(id="a", name="Cafe", area="Hub", category="coffee")
    actor.remember_geo(corridor_snapshot(), [place], _coffee())
    assert actor.reuse_places(_coffee()) is not None
    assert actor.reuse_route(_coffee()) is not None
    assert actor.reuse_places(_coffee(parking_required=True)) is not None
    assert actor.reuse_places(MissionConstraints(category="fuel")) is None
    assert actor.reuse_route(_coffee(avoid_tolls=True)) is None
    actor.commit_revision(_coffee(), "cancelled", True)
    assert actor.reuse_places(_coffee()) is None


def test_new_mission_after_cancel() -> None:
    actor = SessionActor("s1")
    first = actor.commit_revision(_coffee(), "active", True)
    actor.commit_revision(_coffee(), "cancelled", True)
    assert actor.output_gate is OutputGate.CLOSED_FOR_END
    actor.on_user_speaking()
    second = actor.commit_revision(_coffee(parking_required=True), "active", True)
    assert actor.mission_id != first.mission_id
    assert actor.mission_version == 1
    assert second.mission_id == actor.mission_id
    assert actor.output_gate is OutputGate.OPEN
