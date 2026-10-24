"""A tiny asyncio runner pinned to its own thread.

WinRT projections are async, but EkPill is a Qt app. Rather than juggling
qasync, one long-lived event loop lives off the Qt thread and coroutines are
scheduled onto it with :meth:`AsyncLoop.run`.
"""

from __future__ import annotations

import asyncio
import threading


class AsyncLoop:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro) -> None:
        """Fire-and-forget: schedule *coro* and let errors land in the callback."""
        asyncio.run_coroutine_threadsafe(coro, self.loop)
