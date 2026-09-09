from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid
from types import ModuleType

try:
    import livekit.local_inference  # noqa: F401
except Exception:
    fake_native = ModuleType("livekit.local_inference._native")
    fake_native.EOT = type("EOT", (), {})
    fake_native.VAD = type("VAD", (), {})
    fake_native.VAD_WINDOW_SAMPLES = 512
    sys.modules["livekit.local_inference._native"] = fake_native
    fake_local = ModuleType("livekit.local_inference")
    fake_local.EOT = fake_native.EOT
    fake_local.VAD = fake_native.VAD
    fake_local.VAD_WINDOW_SAMPLES = 512
    sys.modules["livekit.local_inference"] = fake_local

from livekit import agents
from livekit.agents import (
    AgentFalseInterruptionEvent,
    AgentServer,
    AgentSession,
    AgentStateChangedEvent,
    CloseEvent,
    ErrorEvent,
    JobContext,
    JobProcess,
    SpeechCreatedEvent,
    UserInputTranscribedEvent,
    UserStateChangedEvent,
    room_io,
)
from livekit.plugins import silero

from .agent import MissionAgent
from .config import REPO_ROOT, get_settings, load_env
from .controller import MissionController
from .events import EventBus
from .persistence import Repository
from .pipeline import build_llm, build_stt, build_tts, build_turn_handling, build_vad
from .rime_catalog import cache_catalog
from .session_actor import SessionActor
from .speech import GREETING
from .tasks import TaskSet


load_env()
logger = logging.getLogger("mid_drive")

GREETING_PLAYOUT_TIMEOUT_S = 20.0


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = build_vad()
    try:
        cache_catalog(get_settings())
        proc.userdata["rime_catalog_warm"] = True
    except Exception as exc:
        proc.userdata["rime_catalog_warm"] = False
        logger.warning("rime catalog prewarm failed: %s", exc)


server = AgentServer(num_idle_processes=1)
server.setup_fnc = prewarm


def _vad_from(ctx: JobContext) -> silero.VAD:
    vad = ctx.proc.userdata.get("vad")
    if isinstance(vad, silero.VAD):
        return vad
    return build_vad()


def _error_kind(error: object) -> str:
    name = type(error).__name__.lower()
    if "stt" in name:
        return "stt"
    if "tts" in name:
        return "tts"
    if "llm" in name:
        return "llm"
    return "runtime"


@server.rtc_session(agent_name="mid-drive")
async def mid_drive(ctx: JobContext) -> None:
    settings = get_settings()
    session_id = uuid.uuid4().hex[:12]
    background = TaskSet()
    bus = EventBus(
        room=ctx.room,
        session_id=session_id,
        log_path=REPO_ROOT / "artifacts" / f"session-{session_id}.jsonl",
    )
    repository = Repository(settings.database_path)
    await repository.init()
    actor = SessionActor(session_id, geo_mode=settings.geo_mode)
    controller = MissionController(
        actor=actor,
        bus=bus,
        repository=repository,
        settings=settings,
    )

    session = AgentSession(
        vad=_vad_from(ctx),
        stt=build_stt(settings),
        llm=build_llm(settings),
        tts=build_tts(settings),
        turn_handling=build_turn_handling(),
    )
    controller.bind_session(session)
    controller.publish_corridor()

    @session.on("user_state_changed")
    def _on_user_state(ev: UserStateChangedEvent) -> None:
        if ev.new_state == "speaking":
            controller.on_user_speaking()
            return
        if ev.new_state == "listening":
            controller.on_user_listening()
        if ev.new_state == "away":
            controller.on_input_paused()
        background.spawn(
            bus.publish("user_state", {"old": ev.old_state, "new": ev.new_state}),
            name="user-state",
        )

    @session.on("agent_state_changed")
    def _on_agent_state(ev: AgentStateChangedEvent) -> None:
        background.spawn(
            bus.publish("agent_state", {"old": ev.old_state, "new": ev.new_state}),
            name="agent-state",
        )

    @session.on("user_input_transcribed")
    def _on_transcript(ev: UserInputTranscribedEvent) -> None:
        text = (ev.transcript or "").strip()
        if not text:
            return
        event_type = "transcript_final" if ev.is_final else "transcript_partial"
        background.spawn(
            bus.publish(event_type, {"text": text, "is_final": ev.is_final}),
            name="transcript",
        )
        controller.on_transcript(text, ev.is_final)

    @ctx.room.on("data_received")
    def _on_data(packet) -> None:
        topic = getattr(packet, "topic", None)
        if topic and topic not in {"mid-drive-ptt", "mid-drive"}:
            return
        try:
            payload = json.loads(packet.data.decode())
        except Exception:
            return
        if payload.get("type") == "ptt_commit":
            controller.on_ptt_commit()
        elif payload.get("type") == "talk_mode":
            controller.set_input_mode(str(payload.get("mode") or "ptt"))

    @session.on("speech_created")
    def _on_speech(ev: SpeechCreatedEvent) -> None:
        controller.on_speech_created(ev.speech_handle)
        background.spawn(
            bus.publish(
                "speech_created",
                {"source": ev.source, "user_initiated": ev.user_initiated},
            ),
            name="speech-created",
        )

    @session.on("agent_false_interruption")
    def _on_false(ev: AgentFalseInterruptionEvent) -> None:
        controller.on_false_interruption()
        background.spawn(
            bus.publish("false_interruption", {"resumed": ev.resumed}),
            name="false-interruption",
        )

    @session.on("error")
    def _on_error(ev: ErrorEvent) -> None:
        kind = _error_kind(ev.error)
        background.spawn(
            bus.publish(
                "provider_error",
                {"kind": kind, "error": type(ev.error).__name__},
            ),
            name="provider-error",
        )

    @session.on("close")
    def _on_close(ev: CloseEvent) -> None:
        controller.end()
        background.spawn(
            bus.publish("session_closed", {"reason": ev.reason.value if ev.reason else "unknown"}),
            name="session-closed",
        )

    await session.start(
        room=ctx.room,
        agent=MissionAgent(controller),
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(auto_gain_control=True),
            text_output=room_io.TextOutputOptions(sync_transcription=False),
        ),
    )

    labels = settings.provider_labels
    await ctx.room.local_participant.set_attributes(
        {
            "stt.provider": labels["stt"],
            "stt.model": labels["stt_model"],
            "tts.provider": labels["tts"],
            "tts.model": labels["tts_model"],
            "tts.speaker": labels["tts_speaker"],
            "tts.language": labels["tts_language"],
            "tts.transport": labels["tts_transport"],
            "llm.provider": labels["llm"],
            "llm.model": labels["llm_model"],
            "geo.mode": labels["geo"],
            "session.id": session_id,
        }
    )
    await bus.publish("session_started", {"providers": labels, "room": ctx.room.name})
    await bus.publish("mission_snapshot", actor.snapshot().model_dump(mode="json"))

    actor.protect_speech = True
    actor.last_spoken_text = GREETING
    await bus.publish("agent_utterance", {"text": GREETING})
    speech = session.say(GREETING, allow_interruptions=False)
    actor.current_speech_handle = speech
    actor.mark_speech_started()
    try:
        await asyncio.wait_for(speech.wait_for_playout(), timeout=GREETING_PLAYOUT_TIMEOUT_S)
    except TimeoutError:
        logger.warning("greeting playout timed out after %.0fs; session stays open", GREETING_PLAYOUT_TIMEOUT_S)
        await bus.publish("greeting_timeout", {"timeout_s": GREETING_PLAYOUT_TIMEOUT_S})
    finally:
        actor.protect_speech = False


def main() -> None:
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
