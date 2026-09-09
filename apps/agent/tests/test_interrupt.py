from __future__ import annotations

from types import SimpleNamespace

import pytest

from mid_drive.controller import EMPTY_TURN_PROMPT, MissionController
from mid_drive.speech import GREETING
from mid_drive.models import MissionConstraints, PlaceCandidate
from mid_drive.persistence import Repository
from mid_drive.session_actor import SessionActor


class DummyBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def publish(self, event_type: str, payload: dict | None = None) -> None:
        self.events.append((event_type, payload or {}))


class FakeHandle:
    def __init__(self) -> None:
        self.interrupted = False

    def done(self) -> bool:
        return False

    def interrupt(self, force: bool = True) -> None:
        self.interrupted = True


class FakeSession:
    def __init__(self) -> None:
        self.said: list[str] = []
        self.last_handle = FakeHandle()

    def say(self, text: str, **_kwargs) -> FakeHandle:
        self.said.append(text)
        self.last_handle = FakeHandle()
        return self.last_handle


async def _controller(tmp_path) -> tuple[MissionController, DummyBus, FakeSession]:
    actor = SessionActor("s1")
    repo = Repository(tmp_path / "mid.db")
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
async def test_echo_of_greeting_is_ignored(tmp_path) -> None:
    controller, bus, session = await _controller(tmp_path)
    greeting = "I'm with you on the Gurgaon to Delhi drive. What do you need along the way?"
    controller.actor.last_spoken_text = greeting
    controller.actor.on_user_speaking()
    await controller.process_completed_turn("I'm with you on the Gurgaon to Delhi drive")
    assert controller.actor.mission_version == 0
    assert controller.actor.constraints is None
    assert session.said == []
    assert any(kind == "echo_ignored" for kind, _ in bus.events)


@pytest.mark.asyncio
async def test_empty_turn_after_barge_in_asks_repeat(tmp_path) -> None:
    controller, _bus, session = await _controller(tmp_path)
    controller.actor.commit_revision(MissionConstraints(category="coffee"), "active", True)
    controller.actor.last_spoken_text = "Looking for coffee on the way."
    controller.actor.speech_interrupted = True
    await controller.on_empty_turn()
    assert session.said == [EMPTY_TURN_PROMPT]
    await controller.on_empty_turn()
    assert session.said == [EMPTY_TURN_PROMPT]


@pytest.mark.asyncio
async def test_empty_turn_during_idle_finishes_greeting(tmp_path) -> None:
    controller, _bus, session = await _controller(tmp_path)
    controller.actor.last_spoken_text = GREETING
    controller.actor.speech_interrupted = True
    await controller.on_empty_turn()
    assert session.said == [GREETING]


@pytest.mark.asyncio
async def test_backchannel_does_not_repeat_last_line(tmp_path) -> None:
    controller, _bus, session = await _controller(tmp_path)
    actor = controller.actor
    actor.commit_revision(MissionConstraints(category="coffee"), "active", True)
    actor.accept_candidate(
        PlaceCandidate(id="a", name="Chai Point", area="NH 48", category="coffee")
    )
    actor.last_spoken_text = "Chai Point in NH 48 lay-by is on the way."
    actor.speech_interrupted = True
    actor.on_user_speaking()
    await controller.process_completed_turn("uh-huh")
    assert session.said == []
    assert actor.selected is not None
    assert actor.selected.name == "Chai Point"


@pytest.mark.asyncio
async def test_accepted_place_speaks_after_token_consumed(tmp_path) -> None:
    controller, bus, session = await _controller(tmp_path)
    actor = controller.actor
    actor.commit_revision(MissionConstraints(category="coffee"), "active", True)
    token = actor.issue_token("place_search")
    actor.consume_request(token)
    await controller.speak_now("Chai Point in NH 48 lay-by is on the way.", token)
    assert session.said[-1].startswith("Chai Point")
    assert not any(kind == "speech_suppressed" for kind, _ in bus.events)


@pytest.mark.asyncio
async def test_speech_queues_when_barrier_is_closed(tmp_path) -> None:
    controller, bus, session = await _controller(tmp_path)
    actor = controller.actor
    actor.commit_revision(MissionConstraints(category="coffee"), "active", True)
    actor.speech_started_at = 0.0
    actor.on_user_speaking()
    await controller.speak_now("Chai Point in NH 48 lay-by is on the way.")
    assert session.said == []
    assert actor.pending_speech is not None
    actor.reopen_same_mission()
    await controller._flush_pending_speech()
    assert session.said[-1].startswith("Chai Point")


@pytest.mark.asyncio
async def test_mid_sentence_coffee_does_not_speak(tmp_path) -> None:
    controller, _bus, session = await _controller(tmp_path)
    await controller.commit_heard("Find a coffee", "partial_idle")
    await controller.commit_heard("Find a coffee shop near", "listening")
    await controller.commit_heard("Find the-", "final")
    assert session.said == []
    assert controller.actor.constraints is None
    await controller.commit_heard("Find a coffee shop near my route.", "ptt")
    assert controller.actor.constraints is not None
    assert controller.actor.constraints.category == "coffee"
    assert any("coffee" in said.lower() for said in session.said)
    spoken = list(session.said)
    await controller.commit_heard("Find a coffee shop near my route.", "partial_idle")
    assert session.said == spoken


@pytest.mark.asyncio
async def test_parking_after_restated_coffee_explains_dropped_lot(tmp_path) -> None:
    controller, _bus, session = await _controller(tmp_path)
    actor = controller.actor
    actor.commit_revision(MissionConstraints(category="coffee"), "active", True)
    actor.accept_candidate(
        PlaceCandidate(id="c", name="Chai Point", area="NH 48", category="coffee", parking="no")
    )
    actor.reopen_same_mission()
    controller._last_user_raw = "Find me a coffee shop near my route."
    await controller.process_completed_turn(
        "Find me a coffee shop near my route. Wait, I need parking too."
    )
    assert actor.constraints is not None
    assert actor.constraints.parking_required is True
    assert actor.selected is not None
    assert actor.selected.name == "Chai Point"
    spoken = session.said[-1].lower()
    assert "parking required" in spoken
    assert "switching to coffee" not in spoken
    assert "chai point" in spoken
    assert "does not have a parking lot" in spoken
    assert "looking again" not in spoken
    assert "blue tokai" not in spoken


@pytest.mark.asyncio
async def test_parking_too_keeps_chai_point_and_does_not_replan(tmp_path) -> None:
    controller, _bus, session = await _controller(tmp_path)
    actor = controller.actor
    actor.commit_revision(MissionConstraints(category="coffee"), "active", True)
    actor.accept_candidate(
        PlaceCandidate(id="c", name="Chai Point", area="NH 48", category="coffee", parking="no")
    )
    actor.reopen_same_mission()
    started: list[MissionConstraints] = []
    controller._start_plan = started.append  # type: ignore[method-assign]
    await controller.process_completed_turn("Wait, I need parking too.")
    assert actor.selected is not None
    assert actor.selected.name == "Chai Point"
    assert actor.constraints is not None
    assert actor.constraints.parking_required is True
    assert started == []
    assert session.said[-1] == "Got it — parking required. Chai Point does not have a parking lot."


@pytest.mark.asyncio
async def test_parking_too_without_selected_still_replans(tmp_path) -> None:
    controller, _bus, _session = await _controller(tmp_path)
    actor = controller.actor
    actor.commit_revision(MissionConstraints(category="coffee"), "active", True)
    started: list[MissionConstraints] = []
    controller._start_plan = started.append  # type: ignore[method-assign]
    await controller.process_completed_turn("Wait, I need parking too.")
    assert actor.selected is None
    assert actor.constraints is not None
    assert actor.constraints.parking_required is True
    assert started == [actor.constraints]


@pytest.mark.asyncio
async def test_parking_too_commits_without_livekit_final(tmp_path) -> None:
    controller, bus, session = await _controller(tmp_path)
    actor = controller.actor
    actor.commit_revision(MissionConstraints(category="coffee"), "active", True)
    actor.accept_candidate(
        PlaceCandidate(id="c", name="Chai Point", area="NH 48", category="coffee", parking="no")
    )
    actor.reopen_same_mission()
    actor.on_user_speaking()
    await controller.commit_heard("Wait, I need parking too.", "partial_idle")
    assert actor.constraints is not None
    assert actor.constraints.parking_required is True
    assert actor.mission_version == 2
    assert actor.selected is not None
    assert actor.selected.name == "Chai Point"
    assert any("parking required" in said.lower() for said in session.said)
    assert any("does not have a parking lot" in said.lower() for said in session.said)
    assert any(kind == "turn_committed" for kind, _ in bus.events)
    await controller.commit_heard("Wait, I need parking too.", "final")
    parking_lines = [said for said in session.said if "parking required" in said.lower()]
    assert len(parking_lines) == 1
    assert "chai point" in parking_lines[0].lower()
    assert "looking again" not in parking_lines[0].lower()


@pytest.mark.asyncio
async def test_empty_turn_commits_leftover_parking(tmp_path) -> None:
    controller, _bus, session = await _controller(tmp_path)
    actor = controller.actor
    actor.commit_revision(MissionConstraints(category="coffee"), "active", True)
    actor.speech_interrupted = True
    controller._pending_partial = "Wait, I need parking too."
    await controller.on_empty_turn()
    assert actor.constraints is not None
    assert actor.constraints.parking_required is True
    assert any("parking required" in said.lower() for said in session.said)
    assert all("looking again" not in said.lower() for said in session.said)


@pytest.mark.asyncio
async def test_where_is_it_commits_after_two_turns(tmp_path) -> None:
    controller, _bus, session = await _controller(tmp_path)
    actor = controller.actor
    actor.commit_revision(MissionConstraints(category="coffee"), "active", True)
    actor.accept_bundle(
        PlaceCandidate(id="c", name="Chai Point", area="NH 48 lay-by", category="coffee", parking="no"),
        [PlaceCandidate(id="t", name="Third Wave Coffee", area="DLF Phase 2", category="coffee")],
    )
    actor.reopen_same_mission()
    controller._committed_norm = "find a coffee shop near my route the second one"
    controller._last_user_raw = "Find a coffee shop near my route. The second one."
    spoken_before = list(session.said)
    controller.on_transcript("Find a coffee shop near my route. The second one.", True)
    assert session.said == spoken_before
    assert controller._pending_partial == ""
    await controller.commit_heard("Where is it?", "ptt")
    assert actor.selected is not None
    assert actor.selected.name == "Chai Point"
    assert any("nh 48" in said.lower() or "lay-by" in said.lower() for said in session.said)


@pytest.mark.asyncio
async def test_gated_say_interrupts_previous(tmp_path) -> None:
    controller, _bus, session = await _controller(tmp_path)
    actor = controller.actor
    actor.commit_revision(MissionConstraints(category="coffee"), "active", True)
    first = actor.issue_token("speech")
    await controller.gated_say(first, "Looking for coffee on the way.")
    previous = session.last_handle
    actor.speech_started_at = 0.0
    actor.on_user_speaking()
    second = actor.reopen_same_mission()
    await controller.gated_say(second, "Got it — parking required.")
    assert previous.interrupted is True
    assert session.said[-1] == "Got it — parking required."
