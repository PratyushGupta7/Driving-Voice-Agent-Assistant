"""Ten-round stress of real speech traps the judged grammar must survive."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mid_drive.controller import MissionController
from mid_drive.llm_revision import worth_llm_fallback
from mid_drive.models import MissionConstraints, PlaceCandidate
from mid_drive.persistence import Repository
from mid_drive.revision import parse_turn
from mid_drive.session_actor import SessionActor
from mid_drive.turn_commit import looks_answerable, looks_finished


class DummyBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def publish(self, event_type: str, payload: dict | None = None) -> None:
        self.events.append((event_type, payload or {}))


class FakeHandle:
    def done(self) -> bool:
        return False

    def interrupt(self, force: bool = True) -> None:
        return None


class FakeSession:
    def __init__(self) -> None:
        self.said: list[str] = []

    def say(self, text: str, **_kwargs) -> FakeHandle:
        self.said.append(text)
        return FakeHandle()


PITFALLS: list[tuple[str, str | None, str, dict]] = [
    ("And parking.", "coffee", "add", {"parking": True}),
    ("I want parking.", "coffee", "add", {"parking": True}),
    ("Must have parking.", "coffee", "add", {"parking": True}),
    ("What about parking?", "coffee", "inquire", {"kind": "parking"}),
    ("Skip it.", "coffee", "next", {}),
    ("I don't want that.", "coffee", "next", {}),
    ("This is fine.", "coffee", "confirm", {}),
    ("That's perfect.", "coffee", "confirm", {}),
    ("How far is it?", "coffee", "inquire", {"kind": "eta"}),
    ("Which one did you pick?", "coffee", "inquire", {"kind": "why"}),
    ("Tell me about it.", "coffee", "inquire", {"kind": "why"}),
    ("Without any tolls.", "coffee", "add", {"tolls": True}),
    ("Find me the nearest coffee.", None, "create", {"category": "coffee", "brand": None}),
    ("Find a quick coffee.", None, "create", {"category": "coffee", "brand": None}),
    ("What can you do?", None, "inquire", {"kind": "help"}),
    ("How's the drive?", "coffee", "inquire", {"kind": "status"}),
    ("Help me find coffee.", None, "create", {"category": "coffee", "brand": None}),
    ("Can you find coffee.", None, "create", {"category": "coffee", "brand": None}),
    ("Find the perfect coffee shop.", None, "create", {"category": "coffee", "brand": None}),
    ("I'm thirsty.", None, "create", {"category": "coffee", "brand": None}),
    ("I need caffeine.", None, "create", {"category": "coffee", "brand": None}),
    ("I'm low on gas.", None, "create", {"category": "fuel", "brand": None}),
    ("Grab a coffee.", None, "create", {"category": "coffee", "brand": None}),
    ("Find coffee within five minutes.", None, "create", {"category": "coffee", "detour": 5}),
    ("What's taking so long?", "coffee", "inquire", {"kind": "status"}),
    ("Still looking?", "coffee", "inquire", {"kind": "status"}),
    ("I'm hungry.", None, "ambiguous", {}),
    ("Still looking for coffee.", None, "create", {"category": "coffee", "brand": None}),
    ("I don't want parking.", "coffee", "add", {"parking": False}),
]


def _current(category: str | None) -> MissionConstraints | None:
    if category is None:
        return None
    return MissionConstraints(category=category)  # type: ignore[arg-type]


def test_speech_pitfalls_ten_times() -> None:
    for _ in range(10):
        for utterance, category, operation, extra in PITFALLS:
            patch = parse_turn(utterance, _current(category))
            assert patch.operation == operation, f"{utterance} -> {patch.operation}"
            if "category" in extra:
                assert patch.category == extra["category"], utterance
            if "parking" in extra:
                assert patch.parking_required is extra["parking"], utterance
            if "tolls" in extra:
                assert patch.avoid_tolls is extra["tolls"], utterance
            if "kind" in extra:
                assert patch.inquire_kind == extra["kind"], utterance
            if "brand" in extra:
                assert patch.brand_query is extra["brand"], utterance
            if "detour" in extra:
                assert patch.maximum_detour_minutes == extra["detour"], utterance
            assert worth_llm_fallback(utterance, patch) is False
            assert looks_finished(utterance) or looks_answerable(utterance, _current(category))


@pytest.mark.asyncio
async def test_help_and_parking_hold_ten_times(tmp_path) -> None:
    for round_i in range(10):
        actor = SessionActor(f"pit-{round_i}")
        repo = Repository(tmp_path / f"pit-{round_i}.db")
        await repo.init()
        bus = DummyBus()
        controller = MissionController(
            actor=actor,
            bus=bus,
            repository=repo,
            settings=SimpleNamespace(geo_mode="fixture", nlu_mode="rules"),
        )
        session = FakeSession()
        controller.bind_session(session)
        controller._start_plan = lambda *_a, **_k: None  # type: ignore[method-assign]

        await controller.process_completed_turn("What can you do?")
        assert session.said[-1].startswith("I can find coffee")
        assert actor.mission_version == 0

        actor.commit_revision(MissionConstraints(category="coffee"), "active", True)
        actor.accept_bundle(
            PlaceCandidate(id="c", name="Chai Point", area="NH 48", category="coffee", parking="no"),
            [],
        )
        actor.reopen_same_mission()
        await controller.process_completed_turn("And parking.")
        assert actor.constraints is not None and actor.constraints.parking_required is True
        assert actor.selected is not None and actor.selected.name == "Chai Point"
        assert "parking required" in session.said[-1].lower()
        assert actor.cockpit.last_nlu_source == "rules"
        assert actor.cockpit.last_operation == "add"
        assert actor.cockpit.last_ack_ms is not None


def test_cockpit_counts_barrier_and_stale() -> None:
    actor = SessionActor("hud")
    actor.commit_revision(MissionConstraints(category="coffee"), "active", True)
    actor.on_user_speaking()
    actor.note_stale("place_search", 2, 3)
    actor.note_accepted()
    snap = actor.snapshot()
    assert snap.cockpit.barrier_count == 1
    assert snap.cockpit.stale_rejects == 1
    assert snap.cockpit.accepted_results == 1
    assert snap.cockpit.last_stale_kind == "place_search"
    assert snap.cockpit.last_stale_version == 2
    assert snap.cockpit.last_stale_epoch == 3
