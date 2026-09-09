"""Ten-round stress of docs/SCENARIOS.md against the rules parser + controller.

Azure is not on this path. Default pytest must stay offline.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mid_drive.controller import MissionController
from mid_drive.llm_revision import worth_llm_fallback
from mid_drive.models import MissionConstraints, MissionPatch
from mid_drive.persistence import Repository
from mid_drive.providers.plan import fixture_plan
from mid_drive.revision import parse_turn
from mid_drive.session_actor import SessionActor


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


# (utterance, current category or None, expected operation, extra checks)
PARSER_CASES: list[tuple[str, str | None, str, dict]] = [
    ("Find a coffee shop near my route.", None, "create", {"category": "coffee", "parking": None}),
    ("Wait, it needs parking.", "coffee", "add", {"parking": True}),
    ("Wait, I need parking too.", "coffee", "add", {"parking": True}),
    ("Does Chai Point have parking?", "coffee", "inquire", {"kind": "parking"}),
    ("Another one.", "coffee", "next", {}),
    ("Avoid toll roads too.", "coffee", "add", {"tolls": True}),
    ("Keep this one.", "coffee", "confirm", {}),
    ("The second one.", "coffee", "select", {"index": 2}),
    ("Go with Blue Tokai.", "coffee", "select", {"name": "Blue Tokai"}),
    ("Why this one?", "coffee", "inquire", {"kind": "why"}),
    ("How much extra time?", "coffee", "inquire", {"kind": "eta"}),
    ("Does it have parking?", "coffee", "inquire", {"kind": "parking"}),
    ("What's the other option?", "coffee", "inquire", {"kind": "other"}),
    ("Where is it?", "coffee", "inquire", {"kind": "where"}),
    ("Where is the coffee shop?", "coffee", "inquire", {"kind": "where"}),
    ("Are they open?", "coffee", "inquire", {"kind": "hours"}),
    ("Compare them.", "coffee", "inquire", {"kind": "compare"}),
    ("Not that, another one.", "coffee", "next", {}),
    ("Actually, I need fuel.", "coffee", "replace", {"category": "fuel"}),
    ("Need a petrol pump.", None, "create", {"category": "fuel", "brand": None}),
    ("Find something near me.", None, "ambiguous", {}),
    ("Find coffee or fuel.", None, "ambiguous", {}),
    ("Uh-huh.", "coffee", "unrelated", {}),
    ("Cancel the search.", "coffee", "cancel", {}),
    ("Find a pharmacy.", None, "create", {"category": "pharmacy"}),
    ("Find coffee near Cyber Hub.", None, "create", {"landmark": "Cyber Hub"}),
    ("Change destination to India Gate.", "coffee", "add", {"dest": "India Gate"}),
    ("Nearer the start.", "coffee", "add", {"along": "start"}),
    ("Find coffee called Blue Tokai.", None, "create", {"brand": "Blue Tokai"}),
    ("Find coffee with parking within 3 minutes.", None, "create", {"parking": True, "detour": 3}),
    ("That's too far.", "coffee", "add", {"detour": 5}),
    ("How's the weather on the ring road?", "coffee", "unrelated", {}),
    ("Find a medical store.", None, "create", {"category": "pharmacy", "brand": None}),
    ("Take me to a pharmacy.", "coffee", "replace", {"category": "pharmacy", "dest": None}),
    ("Parking chahiye.", "coffee", "add", {"parking": True}),
    ("Yeh wala.", "coffee", "confirm", {}),
    ("Koi aur.", "coffee", "next", {}),
]


def _current(category: str | None) -> MissionConstraints | None:
    if category is None:
        return None
    return MissionConstraints(category=category)  # type: ignore[arg-type]


def _check(patch: MissionPatch, extra: dict) -> None:
    if "category" in extra:
        assert patch.category == extra["category"]
    if "parking" in extra:
        assert patch.parking_required is extra["parking"]
    if "tolls" in extra:
        assert patch.avoid_tolls is extra["tolls"]
    if "kind" in extra:
        assert patch.inquire_kind == extra["kind"]
    if "index" in extra:
        assert patch.select_index == extra["index"]
    if "name" in extra:
        assert extra["name"].lower() in (patch.select_name or "").lower()
    if "brand" in extra:
        assert patch.brand_query == extra["brand"]
    if "landmark" in extra:
        assert patch.landmark_query == extra["landmark"]
    if "dest" in extra:
        assert patch.destination_query == extra["dest"]
    if "along" in extra:
        assert patch.prefer_along == extra["along"]
    if "detour" in extra:
        assert patch.maximum_detour_minutes == extra["detour"]


def test_scenario_parser_ten_times() -> None:
    for _ in range(10):
        for utterance, category, operation, extra in PARSER_CASES:
            patch = parse_turn(utterance, _current(category))
            assert patch.operation == operation, utterance
            _check(patch, extra)
            assert worth_llm_fallback(utterance, patch) is False


def test_parser_latency_ten_rounds() -> None:
    import time

    started = time.perf_counter()
    for _ in range(10):
        for utterance, category, _operation, _extra in PARSER_CASES:
            parse_turn(utterance, _current(category))
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert elapsed_ms < 80, f"rules parser too slow: {elapsed_ms:.1f}ms"


def _wire_fixture(controller: MissionController, session: FakeSession) -> list[str]:
    names: list[str] = []

    def start(constraints) -> None:
        outcome = fixture_plan(constraints, set(controller.actor.rejected_ids))
        if outcome.candidate:
            controller.actor.accept_bundle(outcome.candidate, list(outcome.alternatives))
            names.append(outcome.candidate.name)
        if outcome.route:
            controller.actor.cached_route = outcome.route
        if outcome.spoken:
            session.said.append(outcome.spoken)

    controller._start_plan = start  # type: ignore[method-assign]
    return names


async def _controller(tmp_path, suffix: str) -> tuple[MissionController, DummyBus, FakeSession]:
    actor = SessionActor(f"demo-{suffix}")
    repo = Repository(tmp_path / f"demo-{suffix}.db")
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
    return controller, bus, session


@pytest.mark.asyncio
async def test_judged_demo_path_ten_times(tmp_path) -> None:
    """SCENARIOS 1–6 + 8 + 11: the live judged demo, ten identical rounds."""
    for round_i in range(10):
        controller, bus, session = await _controller(tmp_path, str(round_i))
        actor = controller.actor
        picks = _wire_fixture(controller, session)

        await controller.process_completed_turn("Find a coffee shop near my route.")
        assert actor.mission_version == 1
        assert actor.constraints is not None and actor.constraints.category == "coffee"
        assert actor.constraints.parking_required is False
        assert actor.selected is not None and actor.selected.name == "Chai Point"
        assert "Looking for coffee on the way." in session.said
        assert actor.selected is not None and actor.selected.name == "Chai Point"
        assert any("Chai Point" in said for said in session.said)
        chai_line = next(said for said in session.said if said.startswith("Chai Point"))
        assert "parking lot is available" not in chai_line.lower()
        assert "Blue Tokai" not in chai_line

        await controller.process_completed_turn("Wait, I need parking too.")
        assert actor.mission_version == 2
        assert actor.constraints is not None and actor.constraints.parking_required is True
        assert actor.selected is not None and actor.selected.name == "Chai Point"
        assert session.said[-1] == "Got it — parking required. Chai Point does not have a parking lot."
        assert picks[-1] == "Chai Point"

        await controller.process_completed_turn("Another one.")
        assert actor.mission_version == 2
        assert actor.selected is not None and actor.selected.name == "Blue Tokai Coffee Roasters"
        assert "Looking for another." in session.said
        assert any("Blue Tokai" in said for said in session.said)
        assert "parking lot" in session.said[-1].lower() or any(
            "parking lot" in said.lower() and "Blue Tokai" in said for said in session.said
        )

        await controller.process_completed_turn("Avoid toll roads too.")
        assert actor.mission_version == 3
        assert actor.constraints is not None and actor.constraints.avoid_tolls is True
        assert actor.selected is not None and actor.selected.name == "Starbucks"
        assert any("toll-avoiding" in said.lower() for said in session.said)
        assert any("Starbucks" in said for said in session.said)

        await controller.process_completed_turn("Keep this one.")
        assert actor.mission_version == 3
        assert actor.selected is not None and actor.selected.name == "Starbucks"
        assert session.said[-1] == "Okay, keeping that one."

        await controller.process_completed_turn("The second one.")
        assert actor.mission_version == 3
        assert actor.selected is not None and actor.selected.name == "Blue Tokai Coffee Roasters"

        await controller.process_completed_turn("Where is it?")
        assert "Cyber Hub" in session.said[-1]
        assert actor.mission_version == 3

        await controller.process_completed_turn("Are they open?")
        assert "hours" in session.said[-1].lower()

        await controller.process_completed_turn("Actually, I need fuel.")
        assert actor.constraints is not None and actor.constraints.category == "fuel"
        assert actor.selected is not None and actor.selected.name == "Indian Oil"

        await controller.process_completed_turn("Cancel the search.")
        assert actor.status == "cancelled"
        assert actor.selected is None

        await controller.process_completed_turn("Find a coffee shop.")
        assert actor.mission_version == 1
        assert actor.constraints is not None and actor.constraints.parking_required is True
        assert actor.selected is not None and actor.selected.name == "Blue Tokai Coffee Roasters"
        assert any("keep requiring parking" in said.lower() for said in session.said)

        sources = [payload["source"] for kind, payload in bus.events if kind == "revision_parsed"]
        assert sources
        assert set(sources) == {"rules"}
