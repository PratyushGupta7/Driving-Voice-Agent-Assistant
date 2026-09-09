from __future__ import annotations

import asyncio

import aiohttp
from livekit.agents import (
    APIConnectionError,
    APIConnectOptions,
    APIError,
    APIStatusError,
    APITimeoutError,
    tts,
    utils,
)
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
from livekit.agents.utils import is_given
from livekit.plugins import rime
from livekit.plugins.rime.tts import NUM_CHANNELS

from .rime_pcm import (
    RimeAudioError,
    align_pcm_frames,
    pcm_frame_size,
    pcm_from_rime_body,
    pcm_looks_like_speech,
)
from .speech import sanitize_tts_text


class SafeChunkedStream(rime.tts.ChunkedStream):
    """HTTP PCM: download the whole body, reject junk, play aligned frames only."""

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        text = sanitize_tts_text(self._input_text)
        if not text:
            raise APIError("refusing empty Rime text")
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                pcm = await self._fetch_pcm(text)
                self._emit_all(output_emitter, pcm)
                return
            except (RimeAudioError, APITimeoutError) as exc:
                last_error = exc
                continue
        if isinstance(last_error, APITimeoutError):
            raise last_error
        raise APIError(str(last_error) if last_error else "Rime PCM failed") from last_error

    async def _fetch_pcm(self, text: str) -> bytes:
        payload: dict = {
            "speaker": self._opts.speaker,
            "text": text,
            "modelId": self._opts.model,
            "audioFormat": "pcm",
            "samplingRate": self._tts.sample_rate,
        }
        if self._opts.model == "coda" and self._opts.coda_options is not None:
            if is_given(self._opts.coda_options.lang):
                payload["lang"] = self._opts.coda_options.lang
        elif self._opts.mist_options is not None and is_given(self._opts.mist_options.lang):
            payload["lang"] = self._opts.mist_options.lang

        try:
            async with self._tts._ensure_session().post(
                self._tts._base_url,
                headers={
                    "accept": "audio/pcm",
                    "Authorization": f"Bearer {self._tts._api_key}",
                    "content-type": "application/json",
                },
                json=payload,
                timeout=aiohttp.ClientTimeout(
                    total=self._tts._total_timeout,
                    sock_connect=self._conn_options.timeout,
                ),
            ) as resp:
                resp.raise_for_status()
                body = await resp.read()
                pcm = pcm_from_rime_body(body, resp.content_type)
                if not pcm_looks_like_speech(pcm):
                    raise RimeAudioError("Rime PCM looked like silence or garbage")
                return align_pcm_frames(pcm, pcm_frame_size(self._tts.sample_rate))
        except asyncio.TimeoutError:
            raise APITimeoutError() from None
        except aiohttp.ClientResponseError as exc:
            raise APIStatusError(
                message=exc.message,
                status_code=exc.status,
                request_id=None,
                body=None,
            ) from None
        except (RimeAudioError, APIError):
            raise
        except Exception as exc:
            raise APIConnectionError() from exc

    def _emit_all(self, output_emitter: tts.AudioEmitter, pcm: bytes) -> None:
        output_emitter.initialize(
            request_id=utils.shortuuid(),
            sample_rate=self._tts.sample_rate,
            num_channels=NUM_CHANNELS,
            mime_type="audio/pcm",
        )
        frame = pcm_frame_size(self._tts.sample_rate)
        for offset in range(0, len(pcm), frame):
            output_emitter.push(pcm[offset : offset + frame])
        output_emitter.flush()


class SafeRimeTTS(rime.TTS):
    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> rime.tts.ChunkedStream:
        cleaned = sanitize_tts_text(text)
        if not cleaned:
            raise APIError("refusing empty Rime text")
        if self._use_websocket:
            raise RuntimeError("SafeRimeTTS is HTTP PCM only")
        return SafeChunkedStream(tts=self, input_text=cleaned, conn_options=conn_options)
