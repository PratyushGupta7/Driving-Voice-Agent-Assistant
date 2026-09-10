"""Repeatable official full-duplex proof. No acoustic numbers. No invented shops."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from .config import REPO_ROOT
from .controller import MissionController
from .models import FenceDecision, MissionConstraints, OperationResult, PlaceCandidate
from .persistence import Repository
from .providers.plan import fixture_plan
from .result_fence import ResultFence
from .session_actor import SessionActor

CLAIM = (
    "Once the per-session actor linearizes the user-speech barrier, no artifact "
    "from an older output epoch can enter active mission state, new TTS input, "
    "or user-visible application output."
)


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


def _coffee(**kwargs: object) -> MissionConstraints:
    return MissionConstraints(category="coffee", **kwargs)  # type: ignore[arg-type]


def _result(token, name: str) -> OperationResult:
    return OperationResult(
        token=token,
        operation_id=token.request_id,
        provider="fixture",
        candidate=PlaceCandidate(name=name, area="Cyber Hub", category="coffee", parking="yes"),
    )


async def _official_delay_interrupt(tmp: Path, round_i: int) -> dict:
    """PS full-duplex example: delay a tool, interrupt, change the request, reject stale."""
    actor = SessionActor(f"evidence-{round_i}")
    repo = Repository(tmp / f"evidence-{round_i}.db")
    await repo.init()
    fence = ResultFence(actor, repo)
    actor.commit_revision(_coffee(), "active", True)
    stale = actor.issue_token("place_search")
    actor.on_user_speaking()
    actor.commit_revision(_coffee(parking_required=True, avoid_tolls=True), "active", True)
    live = actor.issue_token("place_search")
    live_decision = await fence.commit(_result(live, "Starbucks"))
    stale_decision = await fence.commit(_result(stale, "Chai Point"))
    spoken = actor.selected.name if actor.selected else None
    return {
        "round": round_i + 1,
        "live_decision": live_decision.value,
        "stale_decision": stale_decision.value,
        "spoken_shop": spoken,
        "stale_named": stale_decision is FenceDecision.ACCEPTED,
        "epoch": actor.output_epoch,
        "version": actor.mission_version,
    }


async def _judged_voice_path(tmp: Path, round_i: int) -> dict:
    actor = SessionActor(f"voice-{round_i}")
    repo = Repository(tmp / f"voice-{round_i}.db")
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

    def start(constraints) -> bool:
        outcome = fixture_plan(constraints, set(controller.actor.rejected_ids))
        if outcome.candidate:
            controller.actor.accept_bundle(outcome.candidate, list(outcome.alternatives))
        if outcome.spoken:
            session.said.append(outcome.spoken)
        return True

    controller._start_plan = start  # type: ignore[method-assign]
    await controller.process_completed_turn("Find a coffee shop near my route.")
    await controller.process_completed_turn("Wait, I need parking too.")
    await controller.process_completed_turn("Another one.")
    await controller.process_completed_turn("Avoid toll roads too.")
    shops = [line for line in session.said if any(name in line for name in ("Chai Point", "Blue Tokai", "Starbucks"))]
    return {
        "round": round_i + 1,
        "final_shop": actor.selected.name if actor.selected else None,
        "version": actor.mission_version,
        "avoid_tolls": bool(actor.constraints and actor.constraints.avoid_tolls),
        "parking": bool(actor.constraints and actor.constraints.parking_required),
        "named_after_parking_hold": "Blue Tokai" not in (session.said[1] if len(session.said) > 1 else ""),
        "lines": shops[-3:],
    }


async def collect(tmp: Path) -> dict:
    official = [await _official_delay_interrupt(tmp, i) for i in range(3)]
    voice = [await _judged_voice_path(tmp, i) for i in range(3)]
    stale_admissions = sum(1 for row in official if row["stale_named"])
    return {
        "claim": CLAIM,
        "official_ps_test": "Inject delay, interrupt, change request, reject stale tool, speak only latest mission.",
        "rounds": 3,
        "stale_admissions": stale_admissions,
        "stale_rejects": sum(1 for row in official if row["stale_decision"] == "stale_rejected"),
        "official": official,
        "judged_voice": voice,
        "limitations": [
            "This command proves the application fence, not acoustic stop latency.",
            "Audible leftover audio can remain in the browser buffer after interrupt.",
            "Do not quote an unmeasured p95.",
        ],
    }


def main() -> None:
    tmp = REPO_ROOT / "artifacts" / "evidence-run"
    tmp.mkdir(parents=True, exist_ok=True)
    payload = asyncio.run(collect(tmp))
    out = REPO_ROOT / "artifacts" / "evidence-fence.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("claim", "rounds", "stale_admissions", "stale_rejects")}, indent=2))
    print(f"wrote {out}")
    if payload["stale_admissions"] != 0:
        raise SystemExit("stale admission — fence failed")


if __name__ == "__main__":
    main()
