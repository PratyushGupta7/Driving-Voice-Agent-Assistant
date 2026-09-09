from __future__ import annotations

from .models import FenceDecision, OperationResult
from .persistence import Repository
from .session_actor import SessionActor


class ResultFence:
    def __init__(self, actor: SessionActor, repository: Repository) -> None:
        self.actor = actor
        self.repository = repository

    async def commit(self, result: OperationResult) -> FenceDecision:
        if not self.actor.may_commit(result.token):
            await self.repository.attach_result_if_head_matches(result, self.actor.snapshot())
            return FenceDecision.STALE_REJECTED

        await self.repository.record_operation(result, "returned")

        if not self.actor.may_commit(result.token):
            await self.repository.attach_result_if_head_matches(result, self.actor.snapshot())
            return FenceDecision.STALE_REJECTED

        accepted = await self.repository.attach_result_if_head_matches(result, self.actor.snapshot())
        if not accepted:
            return FenceDecision.STALE_REJECTED

        if not self.actor.may_emit(result.token):
            await self.repository.note_emission_rejected(result.operation_id)
            return FenceDecision.STALE_REJECTED

        if result.candidate is not None:
            self.actor.accept_bundle(result.candidate, result.alternatives)
        self.actor.consume_request(result.token)
        return FenceDecision.ACCEPTED
