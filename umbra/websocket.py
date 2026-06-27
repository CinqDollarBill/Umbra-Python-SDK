"""Real-time WebSocket feeds for the UMBRA SDK.

UMBRA exposes one connection per feed (the subscription is implicit in the URL — there is
no client->server subscribe protocol). This client manages each of those connections for
you with automatic **reconnect** (exponential backoff), **liveness** tracking (the server
emits a ``heartbeat`` frame on idle), **authentication** (the private user feed carries a
session token), and **subscription recovery** (a dropped feed reconnects to the same URL).

Feeds
-----
* Public, unauthenticated — ``subscribe_nbbo`` / ``subscribe_trades`` / ``subscribe_status``.
  Pass a market (slug or id) for a single market, or omit it for the all-markets stream.
* Private, authenticated — the single ``/ws/user/{user_id}`` feed multiplexes order,
  position, and balance updates. ``subscribe_user`` delivers all of them; the convenience
  ``subscribe_orders`` / ``subscribe_positions`` / ``subscribe_balance`` register handlers
  for one kind each (all share one underlying connection).

Handlers may be plain functions or coroutines. Channel handlers receive the inner payload
(an NBBO dict, a print dict, an order dict, ...); register a global ``on("error", ...)`` /
``on("heartbeat", ...)`` to observe lifecycle frames. Every frame is also available via the
``messages()`` async iterator (sync: ``listen()``).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import websockets

from .auth import Authenticator
from .config import ClientConfig
from .exceptions import WebSocketError
from .markets import Markets

logger = logging.getLogger("umbra.ws")

Handler = Callable[[Any], None | Awaitable[None]]

# Read timeout: the server heartbeats every ~30s, so silence past this means a dead socket.
_READ_TIMEOUT = 75.0
_QUEUE_MAX = 10_000

__all__ = ["AsyncWebSocketClient", "WebSocketClient", "Subscription"]


@dataclass
class Subscription:
    """A handle to one live feed connection."""

    channel: str
    url: str
    _feed: _Feed

    async def unsubscribe(self) -> None:
        """Close this feed connection."""
        await self._feed.stop()


@dataclass
class _Feed:
    """One managed WebSocket connection with reconnect + dispatch."""

    url_factory: Callable[[], Awaitable[str]]
    dispatch: Callable[[dict], Awaitable[None]]
    config: ClientConfig
    name: str
    _task: asyncio.Task | None = None
    _stopped: bool = False
    _fatal: bool = False

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"umbra-ws-{self.name}")

    async def stop(self) -> None:
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    async def _run(self) -> None:
        attempt = 0
        while not self._stopped and not self._fatal:
            try:
                url = await self.url_factory()
                async with websockets.connect(url, open_timeout=self.config.timeout) as ws:
                    attempt = 0  # reset backoff on a successful connect
                    if self.config.debug:
                        logger.debug("umbra.ws connected: %s", self.name)
                    await self._read_loop(ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - any failure -> backoff + reconnect
                if self._stopped or self._fatal:
                    break
                delay = min(self.config.backoff_factor * (2**attempt), self.config.backoff_max)
                if self.config.debug:
                    logger.debug(
                        "umbra.ws %s disconnected (%s); reconnecting in %.1fs",
                        self.name,
                        exc,
                        delay,
                    )
                attempt += 1
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    raise

    async def _read_loop(self, ws) -> None:
        while not self._stopped:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=_READ_TIMEOUT)
            except asyncio.TimeoutError:
                # No heartbeat within the window — treat as dead, force a reconnect.
                await ws.close()
                return
            try:
                frame = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if not isinstance(frame, dict):
                continue
            if frame.get("type") == "error":
                # The server closes after an error frame; do not reconnect a doomed feed.
                self._fatal = True
                await self.dispatch(frame)
                return
            await self.dispatch(frame)


class AsyncWebSocketClient:
    """Async manager for UMBRA's real-time feeds."""

    def __init__(self, config: ClientConfig, auth: Authenticator | None, markets: Markets) -> None:
        self._config = config
        self._auth = auth
        self._markets = markets
        self._feeds: list[_Feed] = []
        self._handlers: dict[str, list[Handler]] = {}
        self._queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=_QUEUE_MAX)

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #
    async def connect(self) -> AsyncWebSocketClient:
        """No-op connect for API symmetry — feeds connect lazily on subscribe."""
        return self

    async def close(self) -> None:
        """Close every feed connection."""
        await asyncio.gather(*(f.stop() for f in self._feeds), return_exceptions=True)
        self._feeds.clear()

    # ------------------------------------------------------------------ #
    # Global handlers + message stream                                  #
    # ------------------------------------------------------------------ #
    def on(self, event: str, handler: Handler) -> None:
        """Register a global handler for an event type (``nbbo``/``trade``/``market_status``/
        ``user``/``order``/``position``/``balance``/``heartbeat``/``error``)."""
        self._handlers.setdefault(event, []).append(handler)

    async def messages(self):
        """Async iterator over every received frame (``{"type", "data"}``)."""
        while True:
            yield await self._queue.get()

    # ------------------------------------------------------------------ #
    # Public feeds                                                       #
    # ------------------------------------------------------------------ #
    async def subscribe_nbbo(
        self, market: str | None = None, handler: Handler | None = None
    ) -> Subscription:
        """Subscribe to NBBO updates for one market (slug/id) or all markets."""
        return await self._subscribe_public("nbbo", market, handler)

    async def subscribe_trades(
        self, market: str | None = None, handler: Handler | None = None
    ) -> Subscription:
        """Subscribe to the anonymized trade tape for one market or all markets."""
        return await self._subscribe_public("trades", market, handler, channel="trade")

    async def subscribe_status(
        self, market: str | None = None, handler: Handler | None = None
    ) -> Subscription:
        """Subscribe to market lifecycle-status changes for one market or all markets."""
        return await self._subscribe_public("status", market, handler, channel="market_status")

    async def _subscribe_public(
        self,
        path: str,
        market: str | None,
        handler: Handler | None,
        *,
        channel: str | None = None,
    ) -> Subscription:
        channel = channel or path
        if handler is not None:
            self.on(channel, handler)
        suffix = ""
        if market is not None:
            market_id = await self._markets.resolve_market_id(market)
            suffix = f"/{market_id}"
        url = f"{self._config.ws_url}/ws/{path}{suffix}"

        async def factory() -> str:
            return url

        return self._start_feed(channel, url, factory)

    # ------------------------------------------------------------------ #
    # Private user feed                                                  #
    # ------------------------------------------------------------------ #
    async def subscribe_user(self, handler: Handler | None = None) -> Subscription:
        """Subscribe to the private feed (order + position + balance frames)."""
        if handler is not None:
            self.on("user", handler)
        return await self._ensure_user_feed()

    async def subscribe_orders(self, handler: Handler | None = None) -> Subscription:
        """Subscribe to live order updates on the private feed."""
        if handler is not None:
            self.on("order", handler)
        return await self._ensure_user_feed()

    async def subscribe_positions(self, handler: Handler | None = None) -> Subscription:
        """Subscribe to live position updates on the private feed."""
        if handler is not None:
            self.on("position", handler)
        return await self._ensure_user_feed()

    async def subscribe_balance(self, handler: Handler | None = None) -> Subscription:
        """Subscribe to live balance updates on the private feed."""
        if handler is not None:
            self.on("balance", handler)
        return await self._ensure_user_feed()

    async def _ensure_user_feed(self) -> Subscription:
        if self._auth is None or not self._auth.can_authenticate:
            raise WebSocketError(
                "the private user feed requires authentication; construct the client with "
                "credentials"
            )
        # Reuse a single user-feed connection for all order/position/balance handlers.
        for f in self._feeds:
            if f.name == "user":
                return Subscription("user", "(user feed)", f)
        user_id = await self._auth.require_user_id()
        base = f"{self._config.ws_url}/ws/user/{user_id}"

        async def factory() -> str:
            token = await self._auth.token()  # refreshed on each (re)connect
            return f"{base}?token={token}"

        return self._start_feed("user", base, factory)

    # ------------------------------------------------------------------ #
    # Dispatch + feed bookkeeping                                        #
    # ------------------------------------------------------------------ #
    def _start_feed(
        self, name: str, url: str, factory: Callable[[], Awaitable[str]]
    ) -> Subscription:
        feed = _Feed(url_factory=factory, dispatch=self._dispatch, config=self._config, name=name)
        self._feeds.append(feed)
        feed.start()
        return Subscription(channel=name, url=url, _feed=feed)

    async def _dispatch(self, frame: dict) -> None:
        # Best-effort enqueue for the messages() stream (drop oldest if full).
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:  # pragma: no cover
                pass
        try:
            self._queue.put_nowait(frame)
        except asyncio.QueueFull:  # pragma: no cover
            pass

        ftype = frame.get("type")
        data = frame.get("data")
        if ftype == "user" and isinstance(data, dict):
            await self._emit("user", data)
            kind = data.get("kind")
            payload = data.get(kind) if kind else data
            await self._emit(kind, payload)
        else:
            # Lifecycle frames (error/heartbeat) carry no ``data`` — hand over the whole frame.
            await self._emit(ftype, data if data is not None else frame)

    async def _emit(self, event: str | None, payload: Any) -> None:
        if not event:
            return
        for handler in self._handlers.get(event, []):
            try:
                result = handler(payload)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # noqa: BLE001 - a handler error must not kill the feed
                logger.exception("umbra.ws handler for %r raised", event)


class WebSocketClient:
    """Synchronous facade over :class:`AsyncWebSocketClient`.

    Subscriptions run on the SDK's background event loop. Handlers therefore fire on that
    loop's thread — keep them quick and thread-safe (e.g. push to a ``queue.Queue``), or use
    :meth:`listen` to pull frames on your own thread.
    """

    def __init__(self, async_ws: AsyncWebSocketClient, run: Callable[[Any], Any]) -> None:
        self._ws = async_ws
        self._run = run

    def connect(self) -> WebSocketClient:
        self._run(self._ws.connect())
        return self

    def on(self, event: str, handler: Handler) -> None:
        self._ws.on(event, handler)

    def subscribe_nbbo(self, market: str | None = None, handler: Handler | None = None):
        return _SyncSub(self._run(self._ws.subscribe_nbbo(market, handler)), self._run)

    def subscribe_trades(self, market: str | None = None, handler: Handler | None = None):
        return _SyncSub(self._run(self._ws.subscribe_trades(market, handler)), self._run)

    def subscribe_status(self, market: str | None = None, handler: Handler | None = None):
        return _SyncSub(self._run(self._ws.subscribe_status(market, handler)), self._run)

    def subscribe_user(self, handler: Handler | None = None):
        return _SyncSub(self._run(self._ws.subscribe_user(handler)), self._run)

    def subscribe_orders(self, handler: Handler | None = None):
        return _SyncSub(self._run(self._ws.subscribe_orders(handler)), self._run)

    def subscribe_positions(self, handler: Handler | None = None):
        return _SyncSub(self._run(self._ws.subscribe_positions(handler)), self._run)

    def subscribe_balance(self, handler: Handler | None = None):
        return _SyncSub(self._run(self._ws.subscribe_balance(handler)), self._run)

    def listen(self):
        """Yield received frames synchronously (blocking generator)."""
        agen = self._ws.messages()
        while True:
            yield self._run(agen.__anext__())

    def close(self) -> None:
        self._run(self._ws.close())


@dataclass
class _SyncSub:
    """Synchronous handle to a feed subscription."""

    _sub: Subscription
    _run: Callable[[Any], Any]

    @property
    def channel(self) -> str:
        return self._sub.channel

    def unsubscribe(self) -> None:
        self._run(self._sub.unsubscribe())
