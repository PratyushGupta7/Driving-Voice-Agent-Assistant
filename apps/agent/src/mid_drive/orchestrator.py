from __future__ import annotations

import asyncio
import time

from .fixtures_data import corridor_snapshot
from .models import FenceDecision, MissionConstraints, OperationResult, WorkToken
from .providers.plan import PlanOutcome, execute_plan
from .result_fence import ResultFence


def fixture_delay_seconds(mission_version: int, geo_mode: str = "fixture") -> float:
    """Artificial delay only in fixture mode so v2 can lose a race on purpose."""
    if (geo_mode or "fixture").lower() != "fixture":
        return 0.0
    if mission_version == 2:
        return 8.0
    return 0.0


def _placeholder_outcome() -> PlanOutcome:
    return PlanOutcome(
        candidate=None,
        alternatives=[],
        route=corridor_snapshot(),
        provider="skipped",
        spoken="",
    )


def _result_for(token: WorkToken, *, provider: str, delay_ms: int = 0, error: str | None = None) -> OperationResult:
    return OperationResult(
        token=token,
        operation_id=token.request_id,
        provider=provider,
        delay_ms=delay_ms,
        error=error,
    )


class PlanRun:
    def __init__(
        self,
        *,
        route_decision: FenceDecision,
        place_decision: FenceDecision,
        spoken: str | None,
        route_result: OperationResult,
        place_result: OperationResult,
        outcome: PlanOutcome,
    ) -> None:
        self.route_decision = route_decision
        self.place_decision = place_decision
        self.spoken = spoken
        self.route_result = route_result
        self.place_result = place_result
        self.outcome = outcome


class PlaceSearchOrchestrator:
    def __init__(self, fence: ResultFence, settings) -> None:
        self.fence = fence
        self.settings = settings

    async def _mark_started(self, token: WorkToken) -> None:
        await self.fence.repository.record_operation(
            _result_for(token, provider=self.settings.geo_mode),
            "started",
        )

    async def plan(
        self,
        route_token: WorkToken,
        place_token: WorkToken,
        constraints: MissionConstraints,
        skip_ids: set[str],
    ) -> PlanRun:
        await self._mark_started(route_token)
        await self._mark_started(place_token)
        delay = fixture_delay_seconds(place_token.mission_version, self.settings.geo_mode)
        started = time.perf_counter()
        if delay:
            await asyncio.sleep(delay)

        actor = self.fence.actor
        stale_before_work = not actor.may_commit(place_token) and not actor.may_commit(route_token)
        delay_ms = int((time.perf_counter() - started) * 1000)
        if stale_before_work:
            outcome = _placeholder_outcome()
            route_result = _result_for(
                route_token, provider="skipped", delay_ms=delay_ms, error="stale_before_plan"
            )
            place_result = _result_for(
                place_token, provider="skipped", delay_ms=delay_ms, error="stale_before_plan"
            )
            return PlanRun(
                route_decision=await self.fence.commit(route_result),
                place_decision=await self.fence.commit(place_result),
                spoken=None,
                route_result=route_result,
                place_result=place_result,
                outcome=outcome,
            )

        outcome = await execute_plan(
            self.settings,
            constraints,
            skip_ids,
            reuse_route=actor.reuse_route(constraints),
            reuse_places=actor.reuse_places(constraints),
        )
        delay_ms = int((time.perf_counter() - started) * 1000)

        route_result = OperationResult(
            token=route_token,
            operation_id=route_token.request_id,
            provider=outcome.provider,
            route=outcome.route,
            delay_ms=delay_ms,
            fallback_used=outcome.fallback_used,
        )
        route_decision = await self.fence.commit(route_result)

        place_result = OperationResult(
            token=place_token,
            operation_id=place_token.request_id,
            provider=outcome.provider,
            candidate=outcome.candidate,
            route=outcome.route,
            alternatives=outcome.alternatives,
            delay_ms=delay_ms,
            fallback_used=outcome.fallback_used,
        )
        place_decision = await self.fence.commit(place_result)

        if route_decision is FenceDecision.ACCEPTED or place_decision is FenceDecision.ACCEPTED:
            actor.remember_geo(outcome.route, outcome.places_cache, constraints)

        spoken = outcome.spoken if place_decision is FenceDecision.ACCEPTED else None
        return PlanRun(
            route_decision=route_decision,
            place_decision=place_decision,
            spoken=spoken,
            route_result=route_result,
            place_result=place_result,
            outcome=outcome,
        )

    async def search(
        self,
        token: WorkToken,
        constraints: MissionConstraints,
        skip_ids: set[str],
    ) -> tuple[FenceDecision, str | None, OperationResult]:
        """Compat wrapper: fence the real place token only. Do not invent a route token."""
        await self._mark_started(token)
        delay = fixture_delay_seconds(token.mission_version, self.settings.geo_mode)
        started = time.perf_counter()
        if delay:
            await asyncio.sleep(delay)
        actor = self.fence.actor
        if not actor.may_commit(token):
            result = _result_for(
                token,
                provider="skipped",
                delay_ms=int((time.perf_counter() - started) * 1000),
                error="stale_before_plan",
            )
            return await self.fence.commit(result), None, result
        outcome = await execute_plan(
            self.settings,
            constraints,
            skip_ids,
            reuse_route=actor.reuse_route(constraints),
            reuse_places=actor.reuse_places(constraints),
        )
        result = OperationResult(
            token=token,
            operation_id=token.request_id,
            provider=outcome.provider,
            candidate=outcome.candidate,
            route=outcome.route,
            alternatives=outcome.alternatives,
            delay_ms=int((time.perf_counter() - started) * 1000),
            fallback_used=outcome.fallback_used,
        )
        decision = await self.fence.commit(result)
        if decision is FenceDecision.ACCEPTED:
            actor.remember_geo(outcome.route, outcome.places_cache, constraints)
        spoken = outcome.spoken if decision is FenceDecision.ACCEPTED else None
        return decision, spoken, result
