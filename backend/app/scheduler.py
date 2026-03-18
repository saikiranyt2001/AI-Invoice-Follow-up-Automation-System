from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Awaitable, Callable


class AutomationScheduler:
    def __init__(
        self,
        *,
        interval_minutes: int,
        is_enabled: Callable[[], bool],
        tick: Callable[[], None],
    ) -> None:
        self._interval_seconds = max(1, interval_minutes) * 60
        self._is_enabled = is_enabled
        self._tick = tick
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._last_tick_at: datetime | None = None
        self._last_success_at: datetime | None = None
        self._last_error: str | None = None
        self._next_run_at: datetime | None = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._running = True
        self._next_run_at = datetime.utcnow()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        if not self._task:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run_loop(self) -> None:
        while self._running:
            now = datetime.utcnow()
            if self._is_enabled() and (self._next_run_at is None or now >= self._next_run_at):
                self._last_tick_at = now
                try:
                    self._tick()
                    self._last_success_at = datetime.utcnow()
                    self._last_error = None
                except Exception as exc:  # pragma: no cover - handled by caller logging/tests through state
                    self._last_error = str(exc)
                finally:
                    self._next_run_at = datetime.utcnow() + timedelta(seconds=self._interval_seconds)

            await asyncio.sleep(5)

    def trigger_now(self) -> None:
        self._last_tick_at = datetime.utcnow()
        self._tick()
        self._last_success_at = datetime.utcnow()
        self._last_error = None
        self._next_run_at = datetime.utcnow() + timedelta(seconds=self._interval_seconds)

    def status(self) -> dict[str, object]:
        return {
            "enabled": self._is_enabled(),
            "running": bool(self._task and not self._task.done()),
            "interval_minutes": self._interval_seconds // 60,
            "last_tick_at": self._last_tick_at,
            "last_success_at": self._last_success_at,
            "next_run_at": self._next_run_at,
            "last_error": self._last_error,
        }
