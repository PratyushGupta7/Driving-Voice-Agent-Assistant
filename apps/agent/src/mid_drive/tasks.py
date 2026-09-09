from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger("mid_drive.tasks")


class TaskSet:
    """Tracked tasks so callbacks never fire-and-forget forever."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()

    def spawn(self, coro: Coroutine[Any, Any, Any], *, name: str | None = None) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._on_done)
        return task

    def _on_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.warning("background task failed: %s", exc, exc_info=exc)

    def cancel_all(self) -> None:
        for task in list(self._tasks):
            if not task.done():
                task.cancel()

    def __len__(self) -> int:
        return len(self._tasks)
