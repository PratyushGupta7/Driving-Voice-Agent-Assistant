from __future__ import annotations

import asyncio
import logging
from typing import Any

from livekit.agents import AgentSession

from .events import EventBus
from .fixtures_data import corridor_snapshot
from .models import FenceDecision, MissionConstraints, OperationResult, OutputGate, WorkToken
from .nlu import sanitize_patch
from .orchestrator import PlaceSearchOrchestrator, fixture_delay_seconds
from .persistence import Repository
from .providers.plan import boot_corridor
from .reducer import reduce_mission
from .result_fence import ResultFence
from .revision import parse_turn
from .session_actor import SessionActor
from .speech import GREETING, format_candidate, looks_like_echo, sanitize_tts_text
from .tasks import TaskSet
from .turn_commit import (
    OPEN_FINISHED_IDLE_S,
    PTT_FINISHED_IDLE_S,
    PTT_SETTLE_S,
    is_duplicate_or_shorter,
    is_material_followup,
    is_same_utterance,
    looks_answerable,
    looks_finished,
    normalize_turn,
    peel_restated_prefix,
)

logger = logging.getLogger("mid_drive.controller")

EMPTY_TURN_PROMPT = "I stopped. Please repeat the change."


def _label_for(decision: str) -> str:
    return {
        "accepted": "ACCEPTED",
        "stale_rejected": "OBSOLETE",
        "failed": "FAILED",
        "cancelled": "CANCEL_REQUESTED",
        "cancel_requested": "CANCEL_REQUESTED",
        "running": "STARTED",
    }.get(decision, decision.upper())


class MissionController:
    def __init__(
        self,
        *,
        actor: SessionActor,
        bus: EventBus,
        repository: Repository,
        settings: Any,
    ) -> None:
        self.actor = actor
        self.bus = bus
        self.repository = repository
        self.settings = settings
        self.session: AgentSession | None = None
        self.background = TaskSet()
        self.orchestrator = PlaceSearchOrchestrator(ResultFence(actor, repository), settings)
        self._heard_lock = asyncio.Lock()
        self._pending_partial = ""
        self._partial_gen = 0
        self._committed_norm = ""
        self._last_user_raw = ""
        self._input_mode = "ptt"

    def bind_session(self, session: AgentSession) -> None:
        self.session = session

    def on_transcript(self, text: str, is_final: bool) -> None:
        cleaned = " ".join((text or "").split()).strip()
        if not cleaned:
            return
        if looks_like_echo(cleaned, self.actor.last_spoken_text):
            return
        key = normalize_turn(cleaned)
        if self._committed_norm and is_duplicate_or_shorter(self._committed_norm, key):
            return
        self._pending_partial = cleaned
        if is_final and looks_answerable(cleaned, self.actor.constraints):
            self.background.spawn(self.commit_heard(cleaned, "final"), name="commit-final")
            return
        if not looks_finished(cleaned):
            return
        self._partial_gen += 1
        gen = self._partial_gen
        self.background.spawn(self._idle_commit(gen, cleaned), name="commit-idle")

    async def _idle_commit(self, gen: int, text: str) -> None:
        delay = PTT_FINISHED_IDLE_S if self._input_mode == "ptt" else OPEN_FINISHED_IDLE_S
        await asyncio.sleep(delay)
        if gen != self._partial_gen or self._pending_partial != text:
            return
        if not looks_answerable(text, self.actor.constraints):
            return
        await self.commit_heard(text, "partial_idle")

    def set_input_mode(self, mode: str) -> None:
        self._input_mode = "open" if mode == "open" else "ptt"

    def on_ptt_commit(self) -> None:
        self.background.spawn(self._ptt_commit(), name="commit-ptt")

    async def _ptt_commit(self) -> None:
        await asyncio.sleep(PTT_SETTLE_S)
        text = self._pending_partial
        if text:
            await self.commit_heard(text, "ptt")

    def on_input_paused(self) -> None:
        self.background.spawn(self._flush_pending_on_pause(), name="flush-pause")

    async def _flush_pending_on_pause(self) -> None:
        text = self._pending_partial
        if text and looks_answerable(text, self.actor.constraints):
            await self.commit_heard(text, "input_paused")

    async def commit_heard(self, text: str, reason: str) -> None:
        """Own the turn. LiveKit finals often never arrive once PTT mutes the mic."""
        cleaned = " ".join((text or "").split()).strip()
        if not cleaned:
            return
        if looks_like_echo(cleaned, self.actor.last_spoken_text):
            self.actor.consume_speech_interrupted()
            if self.actor.output_gate != OutputGate.CLOSED_FOR_END:
                self.actor.reopen_same_mission()
            await self.bus.publish("echo_ignored", {"preview": cleaned[:80], "reason": reason})
            return
        forced = reason in {"ptt", "empty_turn", "agent_turn", "input_paused"}
        if not looks_finished(cleaned) and not (
            forced and looks_answerable(cleaned, self.actor.constraints)
        ):
            await self.bus.publish(
                "turn_held",
                {"text": cleaned[:120], "reason": reason, "why": "unfinished"},
            )
            return
        key = normalize_turn(cleaned)
        async with self._heard_lock:
            if is_duplicate_or_shorter(self._committed_norm, key):
                return
            if self.actor.output_gate == OutputGate.CLOSED_FOR_END:
                return
            if is_same_utterance(self._committed_norm, key):
                patch = parse_turn(cleaned, self.actor.constraints)
                if not is_material_followup(patch):
                    return
            self._committed_norm = key
            self._pending_partial = ""
            self.actor.consume_speech_interrupted()
            await self.bus.publish("transcript_final", {"text": cleaned, "is_final": True, "reason": reason})
            await self.bus.publish("turn_committed", {"text": cleaned, "reason": reason})
            await self.process_completed_turn(cleaned)

    def on_speech_created(self, handle: Any) -> None:
        self.actor.current_speech_handle = handle

    def on_user_speaking(self) -> None:
        snap = self.actor.on_user_speaking()
        if snap is None:
            self.background.spawn(
                self.bus.publish("echo_holdoff", {"reason": "greeting_or_onset"}),
                name="echo-holdoff",
            )
            return
        cancelled = self.actor.cancel_obsolete_tasks()
        self.background.spawn(self._publish_barrier(snap.model_dump(mode="json"), cancelled), name="barrier")

    def on_user_listening(self) -> None:
        self.background.spawn(self._flush_pending_speech(), name="flush-speech")

    async def _flush_pending_speech(self) -> None:
        text = self.actor.take_pending_speech()
        if not text or self.actor.output_gate == OutputGate.CLOSED_FOR_END:
            return
        token = self.actor.reopen_same_mission()
        await self.gated_say(token, text)

    async def speak_now(self, text: str, token: WorkToken | None = None) -> None:
        cleaned = sanitize_tts_text(text)
        if not cleaned:
            return
        if token is not None and self.actor.may_emit(token):
            await self.gated_say(token, cleaned)
            return
        if self.actor.output_gate == OutputGate.CLOSED_FOR_INPUT:
            self.actor.queue_speech(cleaned)
            await self.bus.publish("speech_queued", {"preview": cleaned[:80]})
            return
        if self.actor.output_gate == OutputGate.CLOSED_FOR_END:
            return
        await self.gated_say(self.actor.reopen_same_mission(), cleaned)

    def on_false_interruption(self) -> None:
        if self.actor.output_gate == OutputGate.CLOSED_FOR_END:
            return
        text = self.actor.last_spoken_text
        token = self.actor.reopen_same_mission()
        self.background.spawn(self._recover_false_interruption(token, text), name="false-interrupt")

    async def _recover_false_interruption(self, token: WorkToken, text: str | None) -> None:
        await self.bus.publish("false_interruption", {"resumed_under_new_epoch": True})
        await self._publish_live_snapshot()
        if text:
            await self.gated_say(token, text)

    async def _publish_barrier(self, onset: dict[str, Any], cancelled: int) -> None:
        await self.repository.persist_snapshot(self.actor.snapshot(), write_version=False)
        live = self.actor.snapshot().model_dump(mode="json")
        await self.bus.publish(
            "user_state",
            {
                "old": "listening",
                "new": "speaking",
                "barrier": "user_speech_onset",
                "label": "BARRIER_CLOSED",
                "output_epoch": onset["output_epoch"],
                "mission_version": live["mission_version"],
                "output_gate": live["output_gate"],
                "cancelled_tasks": cancelled,
                "interrupted_speech": self.actor.speech_interrupted,
                "barrier_ms": self.actor.last_barrier_ms,
            },
        )
        await self.bus.publish("mission_snapshot", live)

    async def on_empty_turn(self) -> None:
        leftover = self._pending_partial
        if leftover and looks_answerable(leftover, self.actor.constraints):
            await self.commit_heard(leftover, "empty_turn")
            return
        if self.actor.output_gate == OutputGate.CLOSED_FOR_END:
            return
        if not self.actor.consume_speech_interrupted():
            return
        token = self.actor.reopen_same_mission()
        await self._publish_live_snapshot()
        if self.actor.status == "idle" and self.actor.constraints is None:
            await self.gated_say(token, GREETING)
            return
        await self.gated_say(token, EMPTY_TURN_PROMPT)

    async def process_completed_turn(self, text: str) -> None:
        original = text
        text = peel_restated_prefix(text, self._last_user_raw)
        if looks_like_echo(text, self.actor.last_spoken_text):
            self.actor.consume_speech_interrupted()
            self.actor.consume_search_cancelled()
            if self.actor.output_gate != OutputGate.CLOSED_FOR_END:
                self.actor.reopen_same_mission()
            await self.bus.publish("echo_ignored", {"preview": text[:80]})
            await self._publish_live_snapshot()
            return
        self._last_user_raw = original
        patch = sanitize_patch(
            parse_turn(text, self.actor.constraints),
            text,
            self.actor.offered(),
        )
        await self.bus.publish(
            "revision_parsed",
            {
                "text": text,
                "source": "rules",
                "operation": patch.operation,
                "select_index": patch.select_index,
                "inquire_kind": patch.inquire_kind,
            },
        )
        self.actor.note_prefs(patch.parking_required, patch.avoid_tolls)
        reduced = reduce_mission(self.actor.constraints, patch, self.actor.prefs)

        if patch.operation == "unrelated":
            await self._handle_unrelated(text)
            return

        if patch.operation == "select":
            token = self.actor.reopen_same_mission()
            chosen = self.actor.select_offered(patch.select_index, patch.select_name)
            if chosen is None and patch.select_index == 2 and self.actor.constraints is not None:
                self.actor.reject_selected()
                if self.actor.status == "active":
                    self._start_plan(self.actor.constraints)
                await self._persist_and_publish(text)
                await self.gated_say(token, "Looking for another.")
                return
            await self._persist_and_publish(text)
            if chosen is None:
                await self.gated_say(token, "I do not have that option yet. Ask me to search first.")
                return
            spoken = (
                format_candidate(self.actor.constraints, chosen, self.actor.alternatives)
                if self.actor.constraints
                else f"Okay, {chosen.name}."
            )
            await self._publish_accepted_map(token, chosen)
            await self.gated_say(token, spoken)
            return

        if patch.operation == "inquire":
            token = self.actor.reopen_same_mission()
            await self._persist_and_publish(text)
            await self.gated_say(token, self.actor.inquire(patch.inquire_kind or "why"))
            return

        if patch.operation == "confirm":
            token = self.actor.reopen_same_mission()
            await self._persist_and_publish(text)
            if self.actor.selected:
                await self.gated_say(token, reduced.acknowledgement or "Okay, keeping that one.")
            else:
                await self.gated_say(token, "I do not have a place to keep yet.")
            return

        if patch.operation == "next":
            self.actor.reject_selected()
            token = self.actor.reopen_same_mission()
            if self.actor.constraints is not None and self.actor.status == "active":
                self._start_plan(self.actor.constraints)
            await self._persist_and_publish(text)
            if reduced.acknowledgement:
                await self.gated_say(token, reduced.acknowledgement)
            return

        if patch.operation == "ambiguous" or reduced.status == "clarifying":
            token = self.actor.reopen_same_mission()
            self.actor.status = "clarifying"
            await self._persist_and_publish(text)
            if reduced.acknowledgement:
                await self.gated_say(token, reduced.acknowledgement)
            return

        if reduced.changed:
            dropped = self.actor.selected
            hold = self._hold_place_on_parking_add(patch, dropped)
            token = self.actor.commit_revision(
                reduced.constraints, reduced.status, True, keep_places=hold
            )
            if (
                reduced.replan
                and not hold
                and reduced.status == "active"
                and self.actor.constraints is not None
            ):
                self._start_plan(self.actor.constraints)
            await self._persist_and_publish(text)
            spoken = self._parking_revision_speech(patch, reduced.acknowledgement, dropped)
            if spoken:
                await self.gated_say(
                    token,
                    spoken,
                    allow_end=reduced.status == "cancelled",
                )
            return

        self.actor.reopen_same_mission()
        await self._persist_and_publish(text)

    def _hold_place_on_parking_add(self, patch, dropped) -> bool:
        if dropped is None or patch.parking_required is not True:
            return False
        if patch.operation not in {"add", "create"}:
            return False
        extras = (
            patch.avoid_tolls,
            patch.maximum_detour_minutes,
            patch.category,
            patch.landmark_query,
            patch.destination_query,
            patch.origin_query,
            patch.brand_query,
            patch.prefer_along,
        )
        return all(item is None for item in extras)

    def _parking_revision_speech(self, patch, acknowledgement: str | None, dropped) -> str | None:
        if patch.parking_required is True and dropped is not None:
            if dropped.parking == "no":
                return f"Got it — parking required. {dropped.name} does not have a parking lot."
            if dropped.parking == "unknown":
                return f"Got it — parking required. I do not have a parking tag for {dropped.name}."
            if dropped.parking == "yes":
                return f"Got it — parking required. {dropped.name} reports a parking lot."
        return acknowledgement

    async def _handle_unrelated(self, text: str) -> None:
        search_was_cancelled = self.actor.consume_search_cancelled()
        self.actor.consume_speech_interrupted()
        self.actor.reopen_same_mission()
        await self._persist_and_publish(text)
        active = self.actor.status == "active" and self.actor.constraints is not None
        if active and (search_was_cancelled or self.actor.selected is None):
            self._start_plan(self.actor.constraints)

    async def _persist_and_publish(self, source_turn: str) -> None:
        snap = self.actor.snapshot()
        await self.repository.persist_snapshot(
            snap,
            source_turn=source_turn,
            write_version=True,
            input_sequence=self.actor.input_sequence,
        )
        await self.bus.publish("mission_snapshot", snap.model_dump(mode="json"))

    async def _publish_live_snapshot(self) -> None:
        await self.bus.publish("mission_snapshot", self.actor.snapshot().model_dump(mode="json"))

    async def gated_say(self, token: WorkToken, text: str, *, allow_end: bool = False) -> None:
        cleaned = sanitize_tts_text(text)
        if not cleaned:
            return
        if self.session is None:
            self.actor.last_spoken_text = cleaned
            return
        if not self.actor.may_emit(token):
            if not (
                allow_end
                and self.actor.status == "cancelled"
                and token.session_id == self.actor.session_id
            ):
                await self.bus.publish("speech_suppressed", {"reason": "gate_closed", "preview": cleaned[:80]})
                return
        handle = self.actor.current_speech_handle
        if handle is not None and not handle.done() and not self.actor.protect_speech:
            handle.interrupt(force=True)
        self.actor.last_spoken_text = cleaned
        spoken = self.session.say(cleaned, allow_interruptions=not self.actor.protect_speech)
        self.actor.current_speech_handle = spoken
        self.actor.mark_speech_started()
        await self.bus.publish("agent_utterance", {"text": cleaned})

    def publish_corridor(self) -> None:
        self.background.spawn(self._boot_corridor(), name="corridor")

    async def _boot_corridor(self) -> None:
        try:
            route = await boot_corridor(self.settings)
        except Exception:
            route = corridor_snapshot(False)
        await self.bus.publish("map_corridor", route.model_dump(mode="json"))

    def _tool_started(self, token: WorkToken, kind: str) -> None:
        delay = fixture_delay_seconds(token.mission_version, self.settings.geo_mode)
        self.background.spawn(
            self.bus.publish(
                "tool_update",
                {
                    "phase": "started",
                    "kind": kind,
                    "provider": self.settings.geo_mode,
                    "decision": "running",
                    "label": "STARTED",
                    "mission_version": token.mission_version,
                    "output_epoch": token.output_epoch,
                    "request_id": token.request_id,
                    "delay_s": delay,
                },
            ),
            name=f"tool-started-{kind}",
        )

    def _start_plan(self, constraints: MissionConstraints) -> None:
        if self.actor.output_gate.value != "open":
            return
        route_token = self.actor.issue_token("route")
        place_token = self.actor.issue_token("place_search")
        self._tool_started(route_token, "route")
        self._tool_started(place_token, "place_search")
        task = self.background.spawn(
            self._run_plan(route_token, place_token, constraints),
            name="mission-plan",
        )
        self.actor.register_task(route_token.request_id, task)
        self.actor.register_task(place_token.request_id, task)

    def _finished_payload(
        self,
        token: WorkToken,
        kind: str,
        decision: FenceDecision,
        result,
        *,
        name: str | None = None,
        area: str | None = None,
    ) -> dict[str, Any]:
        return {
            "phase": "finished",
            "kind": kind,
            "provider": result.provider,
            "decision": decision.value,
            "label": _label_for(decision.value),
            "mission_version": token.mission_version,
            "output_epoch": token.output_epoch,
            "request_id": token.request_id,
            "delay_ms": result.delay_ms,
            "name": name if decision is FenceDecision.ACCEPTED else None,
            "area": area if decision is FenceDecision.ACCEPTED else None,
            "fallback_used": result.fallback_used,
        }

    async def _run_plan(
        self,
        route_token: WorkToken,
        place_token: WorkToken,
        constraints: MissionConstraints,
    ) -> None:
        try:
            run = await self.orchestrator.plan(
                route_token,
                place_token,
                constraints,
                set(self.actor.rejected_ids),
            )
            accepted_place = (
                run.place_result.candidate
                if run.place_decision is FenceDecision.ACCEPTED
                else None
            )
            await self.bus.publish(
                "tool_update",
                self._finished_payload(route_token, "route", run.route_decision, run.route_result),
            )
            await self.bus.publish(
                "tool_update",
                self._finished_payload(
                    place_token,
                    "place_search",
                    run.place_decision,
                    run.place_result,
                    name=accepted_place.name if accepted_place else None,
                    area=accepted_place.area if accepted_place else None,
                ),
            )
            if run.route_decision is FenceDecision.ACCEPTED and run.outcome.route:
                await self.bus.publish("map_corridor", run.outcome.route.model_dump(mode="json"))
            if run.place_decision is FenceDecision.ACCEPTED:
                await self.bus.publish("mission_snapshot", self.actor.snapshot().model_dump(mode="json"))
                await self.bus.publish(
                    "map_update",
                    {
                        "decision": run.place_decision.value,
                        "mission_version": place_token.mission_version,
                        "output_epoch": place_token.output_epoch,
                        "route": run.outcome.route.model_dump(mode="json"),
                        "candidate": accepted_place.model_dump(mode="json") if accepted_place else None,
                        "alternatives": [
                            item.model_dump(mode="json") for item in run.outcome.alternatives
                        ]
                        if accepted_place
                        else [],
                    },
                )
                if run.spoken:
                    await self.speak_now(run.spoken, place_token)
        except asyncio.CancelledError:
            for token, kind in ((route_token, "route"), (place_token, "place_search")):
                await self.repository.record_operation(
                    OperationResult(
                        token=token,
                        operation_id=token.request_id,
                        provider=self.settings.geo_mode,
                    ),
                    "cancel_requested",
                )
                await self.bus.publish(
                    "tool_update",
                    {
                        "phase": "cancelled",
                        "kind": kind,
                        "decision": "cancel_requested",
                        "label": "CANCEL_REQUESTED",
                        "mission_version": token.mission_version,
                        "output_epoch": token.output_epoch,
                        "request_id": token.request_id,
                    },
                )
            raise
        except Exception as exc:
            logger.warning("mission plan failed: %s", exc)
            for token, kind in ((route_token, "route"), (place_token, "place_search")):
                await self.bus.publish(
                    "tool_update",
                    {
                        "phase": "failed",
                        "kind": kind,
                        "decision": FenceDecision.FAILED.value,
                        "label": "FAILED",
                        "mission_version": token.mission_version,
                        "output_epoch": token.output_epoch,
                        "request_id": token.request_id,
                        "error": type(exc).__name__,
                    },
                )

    async def _publish_accepted_map(self, token: WorkToken, chosen) -> None:
        await self.bus.publish("mission_snapshot", self.actor.snapshot().model_dump(mode="json"))
        route = self.actor.cached_route
        await self.bus.publish(
            "map_update",
            {
                "decision": "accepted",
                "mission_version": token.mission_version,
                "output_epoch": token.output_epoch,
                "route": route.model_dump(mode="json") if route else None,
                "candidate": chosen.model_dump(mode="json"),
                "alternatives": [item.model_dump(mode="json") for item in self.actor.alternatives],
            },
        )

    def end(self) -> None:
        self.actor.end_session()
        self.background.cancel_all()
