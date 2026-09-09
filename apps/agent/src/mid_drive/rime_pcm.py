from __future__ import annotations

import array
import math


class RimeAudioError(RuntimeError):
    pass


# 20 ms of mono s16le at 24 kHz. LiveKit drops leftover bytes as "incomplete frame"
# and that leftover is what the driver hears as a blast of noise.
PCM_FRAME_24K = 960


def pcm_frame_size(sample_rate: int) -> int:
    return max(2, (int(sample_rate) // 50) * 2)


def align_pcm_frames(pcm: bytes, frame: int = PCM_FRAME_24K) -> bytes:
    even = pcm[: len(pcm) - (len(pcm) % 2)]
    pad = (-len(even)) % max(2, frame)
    if pad:
        even = even + (b"\x00" * pad)
    return even


def pcm_from_rime_body(data: bytes, content_type: str | None) -> bytes:
    if not data:
        raise RimeAudioError("Rime returned an empty body")
    kind = (content_type or "").split(";")[0].strip().lower()
    if kind and not kind.startswith("audio") and kind not in {"application/octet-stream", ""}:
        raise RimeAudioError(f"Rime content-type was {kind}, not audio")
    head = data.lstrip()[:1]
    if head in {b"{", b"<"}:
        raise RimeAudioError("Rime returned text instead of PCM")
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        marker = data.find(b"data")
        if marker == -1 or marker + 8 >= len(data):
            raise RimeAudioError("Rime WAV body had no data chunk")
        data = data[marker + 8 :]
    if len(data) < 1600:
        raise RimeAudioError(f"Rime PCM too short ({len(data)} bytes)")
    return data[: len(data) - (len(data) % 2)]


def pcm_looks_like_speech(pcm: bytes) -> bool:
    """Reject digital silence. Do not reject merely-loud speech."""
    even = pcm[: len(pcm) - (len(pcm) % 2)]
    if len(even) < 1600:
        return False
    samples = array.array("h")
    samples.frombytes(even)
    step = max(1, len(samples) // 2500)
    peak = 0
    acc = 0.0
    count = 0
    for sample in samples[::step]:
        mag = abs(sample)
        peak = max(peak, mag)
        acc += sample * sample
        count += 1
    rms = math.sqrt(acc / count) if count else 0.0
    return peak >= 250 and rms >= 40
