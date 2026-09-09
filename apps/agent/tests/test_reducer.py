from mid_drive.models import MissionConstraints, MissionPatch
from mid_drive.reducer import reduce_mission


def test_create_sets_defaults() -> None:
    result = reduce_mission(None, MissionPatch(operation="create", category="coffee"))
    assert result.changed is True
    assert result.constraints is not None
    assert result.constraints.category == "coffee"
    assert result.constraints.parking_required is False
    assert result.speak_now is True


def test_none_preserves_previous() -> None:
    current = MissionConstraints(category="coffee", parking_required=True, avoid_tolls=False)
    result = reduce_mission(current, MissionPatch(operation="add", avoid_tolls=True))
    assert result.changed is True
    assert result.constraints is not None
    assert result.constraints.parking_required is True
    assert result.constraints.avoid_tolls is True
    assert result.constraints.category == "coffee"


def test_duplicate_is_idempotent() -> None:
    current = MissionConstraints(category="coffee", parking_required=True)
    result = reduce_mission(current, MissionPatch(operation="add", parking_required=True))
    assert result.changed is False
    assert result.speak_now is False
    assert result.constraints == current


def test_ambiguous_does_not_mutate() -> None:
    current = MissionConstraints(category="fuel")
    result = reduce_mission(
        current,
        MissionPatch(operation="ambiguous", clarification_question="Coffee, fuel, or a pharmacy?"),
    )
    assert result.changed is False
    assert result.constraints == current
    assert result.status == "clarifying"
    assert result.speak_now is True


def test_unrelated_does_not_mutate() -> None:
    current = MissionConstraints(category="pharmacy")
    result = reduce_mission(current, MissionPatch(operation="unrelated"))
    assert result.changed is False
    assert result.constraints == current
    assert result.speak_now is False


def test_cancel_is_terminal() -> None:
    current = MissionConstraints(category="coffee")
    result = reduce_mission(current, MissionPatch(operation="cancel"))
    assert result.changed is True
    assert result.status == "cancelled"
    assert result.speak_now is True


def test_confirm_does_not_replan() -> None:
    current = MissionConstraints(category="coffee")
    result = reduce_mission(current, MissionPatch(operation="confirm"))
    assert result.changed is False
    assert result.replan is False
    assert result.speak_now is True


def test_next_replans_without_version_change() -> None:
    current = MissionConstraints(category="coffee", parking_required=True)
    result = reduce_mission(current, MissionPatch(operation="next"))
    assert result.changed is False
    assert result.replan is True
    assert result.constraints == current


def test_landmark_and_destination_merge() -> None:
    current = MissionConstraints(category="coffee")
    result = reduce_mission(
        current,
        MissionPatch(operation="add", landmark_query="Cyber Hub", destination_query="India Gate"),
    )
    assert result.changed is True
    assert result.constraints is not None
    assert result.constraints.landmark_query == "Cyber Hub"
    assert result.constraints.destination_query == "India Gate"
    assert result.replan is True


def test_replace_category() -> None:
    current = MissionConstraints(category="coffee", parking_required=True)
    result = reduce_mission(current, MissionPatch(operation="replace", category="fuel"))
    assert result.changed is True
    assert result.constraints is not None
    assert result.constraints.category == "fuel"
    assert result.constraints.parking_required is True
