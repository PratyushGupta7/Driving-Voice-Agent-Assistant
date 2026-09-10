"""Lock the official 3:30 demo video path — docs/DEMO_VIDEO_SCRIPT.md."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from mid_drive.controller import MissionController
from mid_drive.models import MissionConstraints, PlaceCandidate
from mid_drive.persistence import Repository
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


async def _controller(tmp_path, suffix: str) -> tuple[MissionController, DummyBus, FakeSession]:
    actor = SessionActor(f"video-{suffix}")
    repo = Repository(tmp_path / f"video-{suffix}.db")
    await repo.init()
    bus = DummyBus()
    controller = MissionController(
        actor=actor,
        bus=bus,
        repository=repo,
        settings=SimpleNamespace(geo_mode="fixture", nlu_mode="rules", fixture_v2_delay_s=0.25),
    )
    session = FakeSession()
    controller.bind_session(session)
    return controller, bus, session


async def _drain(controller: MissionController, timeout_s: float = 2.5) -> None:
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        if len(controller.background) == 0:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("background work did not finish")


@pytest.mark.asyncio
async def test_demo_video_path(tmp_path) -> None:
    controller, bus, session = await _controller(tmp_path, "main")
    actor = controller.actor

    # 1. Create coffee
    await controller.process_completed_turn("Find a coffee shop near my route.")
    await _drain(controller)
    assert actor.mission_version == 1
    assert actor.selected and actor.selected.name == "Chai Point"
    assert "Looking for coffee on the way." in session.said
    assert any("Chai Point" in line for line in session.said)

    # 2. Parking inquire (not constraint)
    await controller.process_completed_turn("Does it have parking?")
    assert actor.mission_version == 1
    assert actor.constraints and actor.constraints.parking_required is False
    assert "no parking lot" in session.said[-1].lower()

    # 3. Interrupt path: parking add + hold
    await controller.process_completed_turn("Wait, I need parking too.")
    assert actor.mission_version == 2
    assert actor.constraints and actor.constraints.parking_required is True
    assert actor.selected and actor.selected.name == "Chai Point"
    assert session.said[-1] == "Got it — parking required. Chai Point does not have a parking lot."

    # 4. Why
    await controller.process_completed_turn("Why this one?")
    assert "Chai Point" in session.said[-1]

    # 5–7. Delayed search + tolls + stale
    await controller.process_completed_turn("Another one.")
    assert actor.search_inflight is True
    await controller.process_completed_turn("What's taking so long?")
    assert "Still searching" in session.said[-1]
    await controller.process_completed_turn("Avoid toll roads too.")
    await _drain(controller)
    assert actor.mission_version == 3
    assert actor.selected and actor.selected.name == "Starbucks"
    assert actor.cockpit.stale_rejects >= 1
    assert actor.cockpit.last_stale_version == 2
    obsolete = [
        p for k, p in bus.events if k == "tool_update" and p.get("label") == "OBSOLETE"
    ]
    assert obsolete
    assert all(p.get("mission_version") == 2 for p in obsolete)

    # 8. Compare
    await controller.process_completed_turn("Compare them.")
    assert "versus" in session.said[-1].lower()

    # 9. Select second
    await controller.process_completed_turn("The second one.")
    assert actor.selected and actor.selected.name == "Blue Tokai Coffee Roasters"

    # 10. Category replace
    await controller.process_completed_turn("Actually, I need fuel.")
    await _drain(controller)
    assert actor.mission_version == 4
    assert actor.constraints and actor.constraints.category == "fuel"
    assert actor.selected and actor.selected.name == "Indian Oil"

    # 11. Where
    await controller.process_completed_turn("Where is it?")
    assert "Indian Oil" in session.said[-1]
    assert "Hero Honda" in session.said[-1] or "NH 48" in session.said[-1]

    sources = {p["source"] for k, p in bus.events if k == "revision_parsed"}
    assert sources == {"rules"}


@pytest.mark.asyncio
async def test_demo_parking_inquire_before_add_is_not_constraint(tmp_path) -> None:
    controller, _bus, session = await _controller(tmp_path, "inquire")
    actor = controller.actor
    actor.commit_revision(MissionConstraints(category="coffee"), "active", True)
    actor.accept_candidate(
        PlaceCandidate(id="c", name="Chai Point", area="NH 48", category="coffee", parking="no")
    )
    actor.reopen_same_mission()
    await controller.process_completed_turn("Does it have parking?")
    assert actor.mission_version == 1
    assert actor.constraints and actor.constraints.parking_required is False
    assert "no parking lot" in session.said[-1].lower()
    assert "Got it — parking required" not in session.said[-1]
