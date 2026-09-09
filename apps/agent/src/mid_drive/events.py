from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from livekit.rtc import Room


def monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


def wall_time() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


class EventBus:
    """Room data packets plus an append-only JSONL audit file.

    File I/O runs in a worker thread so the VAD barrier is never stalled by disk.
    """

    def __init__(self, room: Room, session_id: str, log_path: Path) -> None:
        self.room = room
        self.session_id = session_id
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._seq = 0
        self._lock = asyncio.Lock()

    def _append(self, event: dict[str, Any]) -> None:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, default=str) + "\n")

    async def publish(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        async with self._lock:
            self._seq += 1
            event = {
                "seq": self._seq,
                "session_id": self.session_id,
                "type": event_type,
                "monotonic_ms": monotonic_ms(),
                "wall_time": wall_time(),
                "payload": payload or {},
            }
            await asyncio.to_thread(self._append, event)
        try:
            await self.room.local_participant.publish_data(
                json.dumps(event, default=str),
                reliable=True,
                topic="mid-drive",
            )
        except Exception:
            # Persistence already succeeded; the UI can recover from the next event.
            pass
