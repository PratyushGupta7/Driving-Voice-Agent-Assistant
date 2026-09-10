from __future__ import annotations

from types import SimpleNamespace

import pytest

from mid_drive.controller import MissionController
from mid_drive.models import MissionConstraints, PlaceCandidate
from mid_drive.persistence import Repository
from mid_drive.revision import parse_turn
from mid_drive.session_actor import SessionActor
from mid_drive.turn_commit import looks_answerable, looks_finished, looks_unfinished


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


def _chai() -> PlaceCandidate:
    return PlaceCandidate(
        id="c",
        name="Chai Point",
        area="NH 48 lay-by",
        category="coffee",
        parking="no",
    )


def _third() -> PlaceCandidate:
    return PlaceCandidate(
        id="t",
        name="Third Wave Coffee",
        area="DLF Phase 2",
        category="coffee",
        parking="unknown",
    )


# Demo voice lines the README cue card actually speaks.
SCENARIO_TURNS: list[tuple[str, str, bool]] = [
    ("Find a coffee shop near my route.", "create", True),
    ("Wait, I need parking too.", "add", True),
    ("Does it have parking?", "inquire", True),
    ("Another one.", "next", True),
    ("Avoid toll roads too.", "add", True),
    ("Where is it?", "inquire", True),
    ("The second one.", "select", True),
    ("Keep this one.", "confirm", True),
    ("Why this one?", "inquire", True),
    ("How much extra time?", "inquire", True),
    ("Compare them.", "inquire", True),
    ("Actually I need fuel.", "replace", True),
    ("Find something near me.", "ambiguous", True),
    ("How's the weather on the ring road?", "unrelated", False),
    ("Yeah.", "unrelated", False),
    ("Cancel the search.", "cancel", True),
]


@pytest.mark.asyncio
async def test_scenario_turns_never_stuck_ten_times(tmp_path) -> None:
    assert len(SCENARIO_TURNS) == 16
    for _round in range(10):
        actor = SessionActor(f"s{_round}")
        repo = Repository(tmp_path / f"mid-{_round}.db")
        await repo.init()
        bus = DummyBus()
        controller = MissionController(
            actor=actor,
            bus=bus,
            repository=repo,
            settings=SimpleNamespace(geo_mode="fixture"),
        )
        session = FakeSession()
        controller.bind_session(session)
        controller._start_plan = lambda *_a, **_k: None  # type: ignore[method-assign]

        silent_turns = 0
        for utterance, expected_op, must_speak in SCENARIO_TURNS:
            if expected_op != "create":
                if actor.constraints is None:
                    actor.commit_revision(MissionConstraints(category="coffee"), "active", True)
                if actor.selected is None:
                    actor.accept_bundle(_chai(), [_third()])
                actor.reopen_same_mission()
            before = len(session.said)
            await controller.process_completed_turn(utterance)
            parsed = [payload for kind, payload in bus.events if kind == "revision_parsed"][-1]
            assert parsed["source"] == "rules", utterance
            assert parsed["operation"] == expected_op, f"{utterance} -> {parsed['operation']}"
            spoke = len(session.said) > before
            if must_speak:
                assert spoke, f"silent stuck on: {utterance}"
                assert session.said[-1].strip(), utterance
            else:
                assert spoke is False, f"backchannel spoke: {utterance}"
                silent_turns += 1
        assert silent_turns == 2
        assert [payload for kind, payload in bus.events if kind == "turn_held"] == []


def test_commit_gate_covers_paraphrases_not_fragments() -> None:
    assert looks_unfinished("Find a coffee")
    assert looks_finished("Find a coffee") is False
    assert looks_finished("Find a coffee shop near my route.")
    assert looks_finished("Where is it?")
    assert looks_finished("What's the other option?")
    assert looks_answerable("Wait, I need parking too.")
    assert looks_answerable("Find a") is False


def test_another_option_is_next_other_option_is_inquire() -> None:
    current = MissionConstraints(category="coffee")
    assert parse_turn("So, tell me about another option which has parking.", current).operation == "next"
    assert parse_turn("What's the other option?", current).operation == "inquire"
    assert parse_turn("What's the other option?", current).inquire_kind == "other"
