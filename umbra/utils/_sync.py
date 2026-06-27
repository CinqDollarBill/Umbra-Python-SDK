"""Sync-over-async bridge.

The SDK's business logic is written once, asynchronously. The synchronous
:class:`~umbra.client.UmbraClient` is a thin facade that runs those coroutines on a
dedicated background event loop via :class:`LoopRunner` — so there is no duplicated logic
and the sync API behaves identically to the async one.

A single daemon thread owns one event loop for the client's lifetime. Coroutines are
submitted with :func:`asyncio.run_coroutine_threadsafe` and their results awaited
synchronously. This is robust whether or not the caller already has a running event loop
(unlike ``asyncio.run``, which refuses to nest).
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Awaitable, Coroutine, TypeVar

T = TypeVar("T")

__all__ = ["LoopRunner"]


class LoopRunner:
    """Owns a background asyncio event loop and runs coroutines on it synchronously."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, name="umbra-sdk-loop", daemon=True
        )
        self._thread.start()
        self._closed = False

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """The background event loop (used to schedule WebSocket tasks)."""
        return self._loop

    def run(self, coro: "Coroutine[Any, Any, T] | Awaitable[T]", timeout: float | None = None) -> T:
        """Run ``coro`` on the background loop and block until it returns."""
        if self._closed:
            raise RuntimeError("client is closed")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)  # type: ignore[arg-type]
        return future.result(timeout)

    def close(self) -> None:
        """Stop the background loop and join its thread (idempotent)."""
        if self._closed:
            return
        self._closed = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        # Best-effort loop teardown once the thread has stopped running it.
        try:
            if not self._loop.is_running():
                self._loop.close()
        except Exception:  # pragma: no cover - defensive
            pass
