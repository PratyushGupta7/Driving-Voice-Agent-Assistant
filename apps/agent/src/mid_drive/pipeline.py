from __future__ import annotations

import httpx
from livekit.agents import TurnHandlingOptions
from livekit.plugins import elevenlabs, openai, silero

from .config import Settings
from .rime_catalog import assert_speaker_live
from .rime_tts import SafeRimeTTS


DOMAIN_KEYTERMS = [
    "Gurgaon",
    "Gurugram",
    "Delhi",
    "parking",
    "detour",
    "tolls",
    "pharmacy",
    "coffee",
    "Chai Point",
    "Starbucks",
    "Blue Tokai",
    "Third Wave",
    "Apollo",
    "Indian Oil",
    "Cyber Hub",
    "Connaught Place",
    "India Gate",
]


def build_vad() -> silero.VAD:
    return silero.VAD.load(
        min_speech_duration=0.10,
        min_silence_duration=0.32,
        activation_threshold=0.55,
        sample_rate=16000,
    )


def build_stt(settings: Settings) -> elevenlabs.STT:
    return elevenlabs.STT(
        api_key=settings.eleven_api_key,
        model="scribe_v2_realtime",
        language_code="en",
        sample_rate=16000,
        include_timestamps=True,
        no_verbatim=False,
        keyterms=DOMAIN_KEYTERMS,
    )


def build_llm(settings: Settings) -> openai.LLM:
    return openai.LLM.with_azure(
        model=settings.azure_openai_deployment,
        azure_deployment=settings.azure_openai_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        temperature=0.0,
        max_completion_tokens=40,
        timeout=httpx.Timeout(connect=8.0, read=8.0, write=8.0, pool=8.0),
    )


def build_tts(settings: Settings) -> SafeRimeTTS:
    # Prewarm caches the catalog. Fail-open here so a later catalog blip does not
    # kill an already-validated worker. Preflight and first cache still hard-fail.
    assert_speaker_live(settings, fail_open=True)
    return SafeRimeTTS(
        api_key=settings.rime_api_key,
        model=settings.rime_model,
        speaker=settings.rime_speaker,
        lang=settings.rime_language,
        sample_rate=settings.rime_sample_rate,
        use_websocket=False,
        base_url=settings.rime_endpoint,
    )


def build_turn_handling() -> TurnHandlingOptions:
    """Local LiveKit: VAD-owned turns. Cloud inference.TurnDetector is not used."""
    return TurnHandlingOptions(
        turn_detection="vad",
        endpointing={"mode": "fixed", "min_delay": 0.55, "max_delay": 1.8},
        interruption={
            "enabled": True,
            "mode": "vad",
            "min_duration": 0.35,
            "min_words": 0,
            "false_interruption_timeout": 2.0,
            "resume_false_interruption": False,
            "discard_audio_if_uninterruptible": True,
        },
        preemptive_generation={"enabled": False},
    )
