import pytest

from mid_drive.models import FenceDecision, MissionConstraints, OperationResult
from mid_drive.orchestrator import fixture_delay_seconds
from mid_drive.persistence import Repository
from mid_drive.result_fence import ResultFence
from mid_drive.session_actor import SessionActor


def _coffee(**kwargs: object) -> MissionConstraints:
    return MissionConstraints(category="coffee", **kwargs)  # type: ignore[arg-type]


def _result(token, name: str = "Blue Tokai Coffee Roasters") -> OperationResult:
    from mid_drive.models import PlaceCandidate

    return OperationResult(
        token=token,
        operation_id="op1",
        provider="fixture",
        candidate=PlaceCandidate(
            name=name,
            area="Cyber Hub",
            category="coffee",
            parking="yes",
            detour_minutes=7,
        ),
    )


@pytest.mark.asyncio
async def test_accepts_matching_head(tmp_path) -> None:
    actor = SessionActor("s1")
    repo = Repository(tmp_path / "mid.db")
    await repo.init()
    actor.commit_revision(_coffee(), "active", True)
    await repo.persist_snapshot(actor.snapshot(), "find coffee")
    token = actor.issue_token("place_search")
    fence = ResultFence(actor, repo)
    decision = await fence.commit(_result(token))
    assert decision is FenceDecision.ACCEPTED


@pytest.mark.asyncio
async def test_rejects_stale_version(tmp_path) -> None:
    actor = SessionActor("s1")
    repo = Repository(tmp_path / "mid.db")
    await repo.init()
    actor.commit_revision(_coffee(), "active", True)
    await repo.persist_snapshot(actor.snapshot(), "find coffee")
    stale = actor.issue_token("place_search")
    actor.on_user_speaking()
    actor.commit_revision(_coffee(parking_required=True), "active", True)
    await repo.persist_snapshot(actor.snapshot(), "needs parking")
    fence = ResultFence(actor, repo)
    decision = await fence.commit(_result(stale))
    assert decision is FenceDecision.STALE_REJECTED


@pytest.mark.asyncio
async def test_rejects_stale_epoch_same_version(tmp_path) -> None:
    actor = SessionActor("s1")
    repo = Repository(tmp_path / "mid.db")
    await repo.init()
    actor.commit_revision(_coffee(), "active", True)
    await repo.persist_snapshot(actor.snapshot(), "find coffee")
    stale = actor.issue_token("place_search")
    actor.on_user_speaking()
    actor.reopen_same_mission()
    await repo.persist_snapshot(actor.snapshot(), write_version=False)
    fence = ResultFence(actor, repo)
    decision = await fence.commit(_result(stale))
    assert decision is FenceDecision.STALE_REJECTED


def test_v2_is_the_late_fixture() -> None:
    assert fixture_delay_seconds(1) == 0.0
    assert fixture_delay_seconds(2) == 8.0
    assert fixture_delay_seconds(3) == 0.0


@pytest.mark.asyncio
async def test_accepts_before_persist(tmp_path) -> None:
    actor = SessionActor("s1")
    repo = Repository(tmp_path / "mid.db")
    await repo.init()
    actor.commit_revision(_coffee(), "active", True)
    token = actor.issue_token("place_search")
    fence = ResultFence(actor, repo)
    decision = await fence.commit(_result(token))
    assert decision is FenceDecision.ACCEPTED
    assert actor.selected is not None
    assert actor.selected.name == "Blue Tokai Coffee Roasters"


@pytest.mark.asyncio
async def test_duplicate_completion_is_stale(tmp_path) -> None:
    actor = SessionActor("s1")
    repo = Repository(tmp_path / "mid.db")
    await repo.init()
    actor.commit_revision(_coffee(), "active", True)
    token = actor.issue_token("place_search")
    fence = ResultFence(actor, repo)
    first = await fence.commit(_result(token, "Blue Tokai Coffee Roasters"))
    second = await fence.commit(_result(token, "Ghost Cafe"))
    assert first is FenceDecision.ACCEPTED
    assert second is FenceDecision.STALE_REJECTED
    assert actor.selected is not None
    assert actor.selected.name == "Blue Tokai Coffee Roasters"
