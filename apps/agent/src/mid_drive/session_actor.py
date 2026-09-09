from __future__ import annotations

import time
import uuid
from typing import Any

from livekit.agents.voice.speech_handle import SpeechHandle

from .models import (
    MissionConstraints,
    MissionSnapshot,
    MissionStatus,
    OutputGate,
    PlaceCandidate,
    RouteSnapshot,
    SessionPrefs,
    VersionEntry,
    WorkToken,
    constraint_brief,
)
from .speech import ECHO_HOLDOFF_S, format_inquire


class SessionActor:
    """Single mutation point per voice session. Epoch advances synchronously."""

    def __init__(self, session_id: str, geo_mode: str = "fixture") -> None:
        self.session_id = session_id
        self.geo_mode = geo_mode
        self.mission_id: str | None = None
        self.mission_version = 0
        self.output_epoch = 0
        self.output_gate = OutputGate.CLOSED_FOR_INPUT
        self.input_sequence = 0
        self.status: MissionStatus | str = "idle"
        self.constraints: MissionConstraints | None = None
        self.current_speech_handle: SpeechHandle | None = None
        self.latest_request_id: dict[str, str] = {}
        self.owned_tasks: dict[str, Any] = {}
        self.selected: PlaceCandidate | None = None
        self.alternatives: list[PlaceCandidate] = []
        self.rejected_ids: list[str] = []
        self.last_spoken_text: str | None = None
        self.search_cancelled = False
        self.speech_interrupted = False
        self.cached_route: RouteSnapshot | None = None
        self.cached_places: list[PlaceCandidate] | None = None
        self.cache_category: str | None = None
        self.cache_origin: str = ""
        self.cache_dest: str = ""
        self.cache_avoid_tolls: bool = False
        self.prefs = SessionPrefs()
        self.version_log: list[VersionEntry] = []
        self.last_revision: str | None = None
        self.last_barrier_ms: int | None = None
        self._barrier_started = 0.0
        self._consumed_ids: set[str] = set()
        self.protect_speech = False
        self.speech_started_at = 0.0
        self.pending_speech: str | None = None

    def snapshot(self) -> MissionSnapshot:
        return MissionSnapshot(
            session_id=self.session_id,
            mission_id=self.mission_id,
            mission_version=self.mission_version,
            output_epoch=self.output_epoch,
            output_gate=self.output_gate,
            status=self.status,  # type: ignore[arg-type]
            constraints=self.constraints,
            selected=self.selected,
            alternatives=list(self.alternatives),
            latest_request_id=dict(self.latest_request_id),
            geo_mode=self.geo_mode,
            rejected_ids=list(self.rejected_ids),
            version_log=list(self.version_log),
            last_revision=self.last_revision,
            last_barrier_ms=self.last_barrier_ms,
            route=self.cached_route,
            prefs=self.prefs,
        )

    def note_prefs(self, parking: bool | None, avoid_tolls: bool | None) -> None:
        if parking is True:
            self.prefs.parking_required = True
        elif parking is False:
            self.prefs.parking_required = False
        if avoid_tolls is True:
            self.prefs.avoid_tolls = True
        elif avoid_tolls is False:
            self.prefs.avoid_tolls = False

    def mark_speech_started(self) -> None:
        self.speech_started_at = time.perf_counter()

    def on_user_speaking(self) -> MissionSnapshot | None:
        """Advance the barrier. None means this onset is greeting/echo, not a driver turn."""
        handle = self.current_speech_handle
        speaking = handle is not None and not handle.done()
        if self.protect_speech and speaking:
            return None
        if (
            speaking
            and self.speech_started_at
            and (time.perf_counter() - self.speech_started_at) < ECHO_HOLDOFF_S
        ):
            return None
        started = time.perf_counter()
        self.output_epoch += 1
        self.output_gate = OutputGate.CLOSED_FOR_INPUT
        self.input_sequence += 1
        if speaking:
            handle.interrupt(force=True)
            self.speech_interrupted = True
        self.last_barrier_ms = int((time.perf_counter() - started) * 1000)
        self._barrier_started = started
        return self.snapshot()

    def issue_token(self, request_kind: str) -> WorkToken:
        if self.mission_id is None:
            self.mission_id = uuid.uuid4().hex[:12]
        request_id = uuid.uuid4().hex[:12]
        self.latest_request_id[request_kind] = request_id
        return WorkToken(
            session_id=self.session_id,
            mission_id=self.mission_id,
            mission_version=self.mission_version,
            output_epoch=self.output_epoch,
            input_sequence=self.input_sequence,
            request_id=request_id,
            request_kind=request_kind,
        )

    def commit_revision(
        self,
        constraints: MissionConstraints | None,
        status: str,
        changed: bool,
        keep_places: bool = False,
    ) -> WorkToken:
        starting_fresh = self.status == "cancelled" and status == "active"
        if starting_fresh:
            self.mission_id = uuid.uuid4().hex[:12]
            self.mission_version = 0
            self.latest_request_id.clear()
            self.rejected_ids.clear()
            self.selected = None
            self.alternatives = []
            self.clear_geo_cache()
        if self.mission_id is None:
            self.mission_id = uuid.uuid4().hex[:12]
        if changed:
            self.mission_version += 1
            if not keep_places:
                self.selected = None
                self.alternatives = []
            self.version_log.append(
                VersionEntry(
                    version=self.mission_version,
                    summary=constraint_brief(constraints),
                    epoch=self.output_epoch,
                )
            )
            self.last_revision = constraint_brief(constraints)
        self.constraints = constraints
        self.status = status
        if status != "cancelled":
            self.output_gate = OutputGate.OPEN
        else:
            self.output_gate = OutputGate.CLOSED_FOR_END
            self.selected = None
            self.alternatives = []
            self.constraints = None
            self.clear_geo_cache()
        return self.issue_token("mission")

    def reopen_same_mission(self) -> WorkToken:
        if self.output_gate != OutputGate.CLOSED_FOR_END:
            self.output_gate = OutputGate.OPEN
        return self.issue_token("speech")

    def accept_candidate(self, candidate: PlaceCandidate) -> None:
        self.accept_bundle(candidate, [])

    def accept_bundle(self, candidate: PlaceCandidate, alternatives: list[PlaceCandidate]) -> None:
        self.selected = candidate
        self.alternatives = [item.model_copy() for item in alternatives]

    def offered(self) -> list[PlaceCandidate]:
        items: list[PlaceCandidate] = []
        if self.selected:
            items.append(self.selected)
        items.extend(self.alternatives)
        return items

    def select_offered(self, index: int | None = None, name: str | None = None) -> PlaceCandidate | None:
        pool = self.offered()
        chosen = None
        if index is not None and 1 <= index <= len(pool):
            chosen = pool[index - 1]
        elif name:
            needle = name.lower().strip()
            chosen = next(
                (
                    item
                    for item in pool
                    if needle in item.name.lower() or needle in (item.brand or "").lower() or needle in item.area.lower()
                ),
                None,
            )
        if chosen is None:
            return None
        rest = [item for item in pool if item.id != chosen.id]
        self.selected = chosen
        self.alternatives = rest
        return chosen

    def inquire(self, kind) -> str:
        return format_inquire(kind, self.constraints, self.selected, self.alternatives, self.cached_route)

    def reject_selected(self) -> None:
        selected = self.selected
        alts = list(self.alternatives)
        if selected and selected.id:
            self.rejected_ids.append(selected.id)
        # Parking hold, then "another one": keep lot-tagged alts in play (Blue Tokai).
        # After a parking pick, skip the whole shown set so the next skip can be empty.
        keep_parking_alts = (
            self.constraints is not None
            and self.constraints.parking_required
            and selected is not None
            and selected.parking != "yes"
        )
        self.selected = None
        self.alternatives = []
        for item in alts:
            if not item.id:
                continue
            if keep_parking_alts and item.parking == "yes":
                continue
            self.rejected_ids.append(item.id)

    def remember_geo(
        self,
        route: RouteSnapshot,
        places: list[PlaceCandidate],
        constraints: MissionConstraints,
    ) -> None:
        self.cached_route = route
        self.cached_places = [item.model_copy() for item in places]
        self.cache_category = constraints.category
        self.cache_origin = constraints.origin_query or ""
        self.cache_dest = constraints.destination_query or ""
        self.cache_avoid_tolls = constraints.avoid_tolls

    def reuse_route(self, constraints: MissionConstraints) -> RouteSnapshot | None:
        if self.cached_route is None:
            return None
        if (constraints.origin_query or "") != self.cache_origin:
            return None
        if (constraints.destination_query or "") != self.cache_dest:
            return None
        if constraints.avoid_tolls != self.cache_avoid_tolls:
            return None
        return self.cached_route

    def reuse_places(self, constraints: MissionConstraints) -> list[PlaceCandidate] | None:
        if self.cached_places is None:
            return None
        if constraints.category != self.cache_category:
            return None
        if (constraints.origin_query or "") != self.cache_origin:
            return None
        if (constraints.destination_query or "") != self.cache_dest:
            return None
        return [item.model_copy() for item in self.cached_places]

    def clear_geo_cache(self) -> None:
        self.cached_route = None
        self.cached_places = None
        self.cache_category = None
        self.cache_origin = ""
        self.cache_dest = ""
        self.cache_avoid_tolls = False

    def consume_search_cancelled(self) -> bool:
        flagged = self.search_cancelled
        self.search_cancelled = False
        return flagged

    def consume_speech_interrupted(self) -> bool:
        flagged = self.speech_interrupted
        self.speech_interrupted = False
        return flagged

    def _matches(self, token: WorkToken) -> bool:
        return (
            token.session_id == self.session_id
            and token.mission_id == self.mission_id
            and token.mission_version == self.mission_version
            and token.output_epoch == self.output_epoch
            and self.latest_request_id.get(token.request_kind) == token.request_id
        )

    def may_commit(self, token: WorkToken) -> bool:
        if token.request_id in self._consumed_ids:
            return False
        return self.output_gate == OutputGate.OPEN and self._matches(token)

    def may_emit(self, token: WorkToken) -> bool:
        """Speak current mission audio even after the tool token was consumed."""
        return (
            self.output_gate == OutputGate.OPEN
            and token.session_id == self.session_id
            and token.mission_id == self.mission_id
            and token.mission_version == self.mission_version
            and token.output_epoch == self.output_epoch
        )

    def queue_speech(self, text: str) -> None:
        self.pending_speech = text

    def take_pending_speech(self) -> str | None:
        text = self.pending_speech
        self.pending_speech = None
        return text

    def consume_request(self, token: WorkToken) -> None:
        self._consumed_ids.add(token.request_id)
        if self.latest_request_id.get(token.request_kind) == token.request_id:
            self.latest_request_id[token.request_kind] = f"consumed:{token.request_id}"

    def register_task(self, key: str, task: Any) -> None:
        self.owned_tasks[key] = task

    def cancel_obsolete_tasks(self) -> int:
        cancelled = 0
        seen: set[int] = set()
        for key, task in list(self.owned_tasks.items()):
            done = getattr(task, "done", None)
            is_done = done() if callable(done) else False
            if is_done:
                self.owned_tasks.pop(key, None)
                continue
            cancel = getattr(task, "cancel", None)
            if callable(cancel):
                identity = id(task)
                if identity not in seen:
                    cancel()
                    cancelled += 1
                    seen.add(identity)
                self.owned_tasks.pop(key, None)
        if cancelled:
            self.search_cancelled = True
        return cancelled

    def end_session(self) -> None:
        self.output_gate = OutputGate.CLOSED_FOR_END
        self.cancel_obsolete_tasks()
        if self.current_speech_handle is not None and not self.current_speech_handle.done():
            self.current_speech_handle.interrupt(force=True)
