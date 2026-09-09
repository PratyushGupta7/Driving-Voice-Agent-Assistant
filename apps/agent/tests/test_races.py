from __future__ import annotations

import random
from types import SimpleNamespace

import pytest

from mid_drive.models import FenceDecision, MissionConstraints, OperationResult, PlaceCandidate
from mid_drive.orchestrator import PlaceSearchOrchestrator
from mid_drive.persistence import Repository
from mid_drive.result_fence import ResultFence
from mid_drive.session_actor import SessionActor


def _coffee(**kwargs: object) -> MissionConstraints:
    return MissionConstraints(category="coffee", **kwargs)  # type: ignore[arg-type]


def _result(token, name: str = "Blue Tokai Coffee Roasters") -> OperationResult:
    return OperationResult(
        token=token,
        operation_id=token.request_id,
        provider="fixture",
        candidate=PlaceCandidate(name=name, area="Cyber Hub", category="coffee", parking="yes"),
    )


def _selected_name(actor: SessionActor) -> str | None:
    return actor.selected.name if actor.selected else None


async def _fence(tmp_path, persist: bool = True) -> tuple[SessionActor, ResultFence]:
    actor = SessionActor("race")
    repo = Repository(tmp_path / "race.db")
    await repo.init()
    actor.commit_revision(_coffee(), "active", True)
    if persist:
        await repo.persist_snapshot(actor.snapshot(), "find coffee")
    return actor, ResultFence(actor, repo)


@pytest.mark.asyncio
async def test_v2_before_v1_cannot_admit_v1(tmp_path) -> None:
    actor, fence = await _fence(tmp_path)
    v1 = actor.issue_token("place_search")
    actor.on_user_speaking()
    actor.commit_revision(_coffee(parking_required=True), "active", True)
    await fence.repository.persist_snapshot(actor.snapshot(), "parking")
    v2 = actor.issue_token("place_search")
    assert await fence.commit(_result(v2, "Starbucks")) is FenceDecision.ACCEPTED
    assert await fence.commit(_result(v1, "Chai Point")) is FenceDecision.STALE_REJECTED
    assert _selected_name(actor) == "Starbucks"


@pytest.mark.asyncio
async def test_v1_after_v2_is_stale(tmp_path) -> None:
    actor, fence = await _fence(tmp_path)
    v1 = actor.issue_token("place_search")
    actor.on_user_speaking()
    actor.commit_revision(_coffee(parking_required=True), "active", True)
    v2 = actor.issue_token("place_search")
    assert await fence.commit(_result(v1)) is FenceDecision.STALE_REJECTED
    assert await fence.commit(_result(v2, "Starbucks")) is FenceDecision.ACCEPTED


@pytest.mark.asyncio
async def test_epoch_change_same_version(tmp_path) -> None:
    actor, fence = await _fence(tmp_path)
    stale = actor.issue_token("place_search")
    actor.on_user_speaking()
    actor.reopen_same_mission()
    live = actor.issue_token("place_search")
    assert actor.mission_version == 1
    assert await fence.commit(_result(stale)) is FenceDecision.STALE_REJECTED
    assert await fence.commit(_result(live)) is FenceDecision.ACCEPTED


@pytest.mark.asyncio
async def test_session_end_rejects_in_flight(tmp_path) -> None:
    actor, fence = await _fence(tmp_path)
    token = actor.issue_token("place_search")
    actor.end_session()
    assert await fence.commit(_result(token)) is FenceDecision.STALE_REJECTED
    assert actor.selected is None


@pytest.mark.asyncio
async def test_error_after_success_cannot_replace(tmp_path) -> None:
    actor, fence = await _fence(tmp_path)
    token = actor.issue_token("place_search")
    assert await fence.commit(_result(token)) is FenceDecision.ACCEPTED
    actor.on_user_speaking()
    actor.reopen_same_mission()
    failed = actor.issue_token("place_search")
    boom = OperationResult(token=failed, operation_id=failed.request_id, provider="fixture", error="boom")
    assert await fence.commit(boom) is FenceDecision.ACCEPTED
    assert _selected_name(actor) == "Blue Tokai Coffee Roasters"


@pytest.mark.asyncio
async def test_stale_after_delay_skips_execute_plan(tmp_path, monkeypatch) -> None:
    calls: list[int] = []

    async def boom(*_args, **_kwargs):
        calls.append(1)
        raise AssertionError("execute_plan must not run after the token is stale")

    monkeypatch.setattr("mid_drive.orchestrator.fixture_delay_seconds", lambda *_a, **_k: 0)
    monkeypatch.setattr("mid_drive.orchestrator.execute_plan", boom)
    actor, fence = await _fence(tmp_path)
    route = actor.issue_token("route")
    place = actor.issue_token("place_search")
    actor.on_user_speaking()
    actor.commit_revision(_coffee(parking_required=True), "active", True)
    orch = PlaceSearchOrchestrator(fence, SimpleNamespace(geo_mode="fixture"))
    run = await orch.plan(route, place, _coffee(), set())
    assert calls == []
    assert run.route_decision is FenceDecision.STALE_REJECTED
    assert run.place_decision is FenceDecision.STALE_REJECTED
    assert run.spoken is None


@pytest.mark.asyncio
async def test_property_no_stale_admission(tmp_path) -> None:
    rng = random.Random(2026)
    actor, fence = await _fence(tmp_path, persist=False)
    issued: list = []
    for _ in range(400):
        action = rng.choice(["speak", "revise", "issue", "commit_old", "commit_live", "persist", "end"])
        if action == "speak":
            actor.on_user_speaking()
            if actor.output_gate.value != "closed_for_end":
                actor.reopen_same_mission()
        elif action == "revise" and actor.output_gate.value != "closed_for_end":
            actor.on_user_speaking()
            actor.commit_revision(_coffee(parking_required=rng.random() < 0.5), "active", True)
        elif action == "issue" and actor.output_gate.value == "open":
            issued.append(actor.issue_token("place_search"))
        elif action == "commit_old" and issued:
            token = issued[rng.randrange(len(issued))]
            before = _selected_name(actor)
            decision = await fence.commit(_result(token, "Old Shop"))
            if decision is FenceDecision.ACCEPTED:
                assert _selected_name(actor) == "Old Shop"
                assert actor.may_commit(token) is False
            else:
                assert _selected_name(actor) == before
        elif action == "commit_live" and actor.output_gate.value == "open":
            token = actor.issue_token("place_search")
            issued.append(token)
            before = _selected_name(actor)
            decision = await fence.commit(_result(token, "Live Shop"))
            if decision is FenceDecision.ACCEPTED:
                assert _selected_name(actor) == "Live Shop"
                assert actor.may_commit(token) is False
            else:
                assert _selected_name(actor) == before
        elif action == "persist":
            await fence.repository.persist_snapshot(actor.snapshot(), write_version=False)
        elif action == "end" and rng.random() < 0.08:
            token = actor.issue_token("place_search") if actor.mission_id else None
            actor.end_session()
            if token is not None:
                before = _selected_name(actor)
                assert await fence.commit(_result(token, "After End")) is FenceDecision.STALE_REJECTED
                assert _selected_name(actor) == before
            break
        issued = issued[-16:]
