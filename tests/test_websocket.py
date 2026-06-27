"""WebSocket client tests against a real local server (connect, dispatch, reconnect, error)."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import websockets

from umbra.client import AsyncUmbraClient


def _client(ws_url: str) -> AsyncUmbraClient:
    # REST transport is unused by public WS subscriptions but required to build the client.
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=[]))
    return AsyncUmbraClient(
        api_url="http://unused", ws_url=ws_url, transport=transport,
        backoff_factor=0.0, backoff_max=0.0,
    )


def run(coro):
    return asyncio.run(coro)


def test_nbbo_frame_dispatched():
    async def main():
        async def handler(ws):
            await ws.send(json.dumps({"type": "nbbo", "data": {"market_id": "m1", "best_bid": "0.5"}}))
            await asyncio.sleep(0.2)

        server = await websockets.serve(handler, "localhost", 0)
        port = server.sockets[0].getsockname()[1]
        client = _client(f"ws://localhost:{port}")
        received = []
        got = asyncio.Event()

        def on_nbbo(data):
            received.append(data)
            got.set()

        ws = client.websocket()
        await ws.subscribe_nbbo(handler=on_nbbo)
        try:
            await asyncio.wait_for(got.wait(), timeout=3)
        finally:
            await ws.close()
            server.close()
            await server.wait_closed()
            await client.aclose()

        assert received and received[0]["market_id"] == "m1"

    run(main())


def test_reconnects_after_drop():
    async def main():
        state = {"connects": 0}

        async def handler(ws):
            state["connects"] += 1
            await ws.send(json.dumps({"type": "nbbo", "data": {"market_id": "m1", "n": state["connects"]}}))
            # Drop the connection immediately to force a reconnect.

        server = await websockets.serve(handler, "localhost", 0)
        port = server.sockets[0].getsockname()[1]
        client = _client(f"ws://localhost:{port}")
        seen = []
        twice = asyncio.Event()

        def on_nbbo(data):
            seen.append(data["n"])
            if len(seen) >= 2:
                twice.set()

        ws = client.websocket()
        await ws.subscribe_nbbo(handler=on_nbbo)
        try:
            await asyncio.wait_for(twice.wait(), timeout=5)
        finally:
            await ws.close()
            server.close()
            await server.wait_closed()
            await client.aclose()

        assert state["connects"] >= 2  # reconnected at least once

    run(main())


def test_error_frame_is_fatal_no_reconnect():
    async def main():
        state = {"connects": 0}

        async def handler(ws):
            state["connects"] += 1
            await ws.send(json.dumps({"type": "error", "detail": "UNKNOWN_MARKET"}))
            await asyncio.sleep(0.3)

        server = await websockets.serve(handler, "localhost", 0)
        port = server.sockets[0].getsockname()[1]
        client = _client(f"ws://localhost:{port}")
        errors = []
        err = asyncio.Event()

        def on_error(frame):
            errors.append(frame)
            err.set()

        ws = client.websocket()
        ws.on("error", on_error)
        await ws.subscribe_nbbo()
        try:
            await asyncio.wait_for(err.wait(), timeout=3)
            await asyncio.sleep(0.5)  # give any (incorrect) reconnect a chance to happen
        finally:
            await ws.close()
            server.close()
            await server.wait_closed()
            await client.aclose()

        assert errors and errors[0]["detail"] == "UNKNOWN_MARKET"
        assert state["connects"] == 1  # fatal error -> no reconnect

    run(main())
