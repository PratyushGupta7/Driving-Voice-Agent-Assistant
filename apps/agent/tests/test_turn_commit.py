from mid_drive.models import MissionPatch
from mid_drive.turn_commit import (
    is_duplicate_or_shorter,
    is_material_followup,
    is_same_utterance,
    looks_answerable,
    looks_finished,
    looks_unfinished,
    normalize_turn,
    peel_restated_prefix,
)


def test_fragments_are_unfinished() -> None:
    assert looks_unfinished("Find a")
    assert looks_unfinished("Find the-")
    assert looks_unfinished("Find a coffee")
    assert looks_unfinished("Find a coffee shop near")
    assert looks_unfinished("Find a coffee shop near my...")
    assert looks_unfinished("Wait, I need")
    assert looks_finished("Find a coffee") is False
    assert looks_finished("Find a coffee shop near") is False


def test_finished_requests() -> None:
    assert looks_finished("Find a coffee shop near my route.")
    assert looks_finished("Wait, I need parking too.")
    assert looks_finished("Wait, it needs parking")
    assert looks_finished("Keep this one")
    assert looks_finished("Avoid toll roads too")
    assert looks_finished("I need coffee")
    assert looks_finished("Where is it?")
    assert looks_finished("Are they open?")
    assert looks_finished("Compare them.")
    assert looks_finished("What's the other option?")
    assert looks_finished("The third one.")
    assert looks_finished("Find a coffee") is False
    assert looks_answerable("Where is it?") is True
    assert looks_answerable("Find a") is False


def test_duplicate_and_continuation() -> None:
    first = normalize_turn("Wait, I need parking")
    later = normalize_turn("Wait, I need parking too.")
    assert is_duplicate_or_shorter(first, first)
    assert is_duplicate_or_shorter(later, first)
    assert is_duplicate_or_shorter(first, later) is False
    assert is_same_utterance(
        normalize_turn("Find a coffee"),
        normalize_turn("Find a coffee shop near my route."),
    )
    assert is_material_followup(MissionPatch(operation="add")) is False
    assert is_material_followup(MissionPatch(operation="add", parking_required=True)) is True


def test_peel_restated_coffee_sentence() -> None:
    previous = "Find me a coffee shop near my route."
    full = "Find me a coffee shop near my route. Wait, I need parking too."
    assert peel_restated_prefix(full, previous) == "wait i need parking too"
