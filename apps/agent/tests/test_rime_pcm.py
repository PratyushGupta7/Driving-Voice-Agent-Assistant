from mid_drive.rime_pcm import (
    RimeAudioError,
    align_pcm_frames,
    pcm_frame_size,
    pcm_from_rime_body,
    pcm_looks_like_speech,
)
from mid_drive.speech import looks_like_echo, sanitize_tts_text
import pytest


def _pcm(peak: int = 4000, count: int = 2000) -> bytes:
    return b"".join((peak if i % 2 == 0 else -peak).to_bytes(2, "little", signed=True) for i in range(count))


def test_rejects_json_and_html() -> None:
    with pytest.raises(RimeAudioError):
        pcm_from_rime_body(b'{"error":"nope"}', "application/json")
    with pytest.raises(RimeAudioError):
        pcm_from_rime_body(b"<html>fail</html>", "text/html")


def test_strips_wav_wrapper() -> None:
    pcm = _pcm()
    header = b"RIFF" + (36 + len(pcm)).to_bytes(4, "little") + b"WAVEfmt "
    header += (16).to_bytes(4, "little") + b"\x01\x00\x01\x00"
    header += (24000).to_bytes(4, "little") + (48000).to_bytes(4, "little")
    header += b"\x02\x00\x10\x00data" + len(pcm).to_bytes(4, "little")
    out = pcm_from_rime_body(header + pcm, "audio/wav")
    assert out == pcm
    assert pcm_looks_like_speech(out)


def test_rejects_silence_and_tiny() -> None:
    with pytest.raises(RimeAudioError):
        pcm_from_rime_body(b"\x00" * 20, "audio/pcm")
    silence = b"\x00" * 4000
    assert pcm_from_rime_body(silence, "audio/pcm") == silence
    assert pcm_looks_like_speech(silence) is False


def test_pcm_frames_are_aligned() -> None:
    assert pcm_frame_size(24000) == 960
    leftover = b"\x01\x00\x02\x00\x03"
    aligned = align_pcm_frames(leftover, 8)
    assert len(aligned) % 8 == 0
    assert aligned[:4] == b"\x01\x00\x02\x00"


def test_sanitize_and_echo() -> None:
    assert sanitize_tts_text("**Hello**") == "Hello"
    assert "http" not in sanitize_tts_text("See https://example.com now")
    assert sanitize_tts_text("1234") == ""
    spoken = "I'm with you on the Gurgaon to Delhi drive. What do you need along the way?"
    assert looks_like_echo("I'm with you on the Gurgaon to Delhi drive", spoken)
    assert looks_like_echo("I'm with you on", spoken)
    assert looks_like_echo("Find a coffee shop near my route", spoken) is False
    parking_line = "Got it — parking required. Chai Point does not have a parking lot."
    assert looks_like_echo("Does it have parking?", parking_line) is False
    assert looks_like_echo("Where is it?", "Chai Point in NH 48 lay-by is on the way.") is False
    assert looks_like_echo(
        "Keep this one.",
        "Chai Point in NH 48 lay-by is on the way. Should I keep this one?",
    ) is False
