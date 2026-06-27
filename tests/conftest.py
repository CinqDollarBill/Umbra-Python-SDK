"""Shared test fixtures.

Tests drive the SDK through an ``httpx.MockTransport`` so no network or running exchange is
needed. A small router lets each test register handlers per ``(method, path)`` and records
the requests the SDK actually made (so we can assert on body/params/headers).
"""

from __future__ import annotations

import base64
import json
from typing import Callable, Dict, List, Tuple

import httpx
import pytest
from eth_account import Account

from umbra import Client


class MockServer:
    """A tiny routable mock backend with request recording."""

    def __init__(self) -> None:
        self.routes: Dict[Tuple[str, str], Callable[[httpx.Request], httpx.Response]] = {}
        self.requests: List[httpx.Request] = []

    def route(self, method: str, path: str):
        def register(fn):
            self.routes[(method.upper(), path)] = fn
            return fn
        return register

    def json_route(self, method: str, path: str, payload, status: int = 200) -> None:
        self.routes[(method.upper(), path)] = lambda req: httpx.Response(status, json=payload)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        handler = self.routes.get((request.method, request.url.path))
        if handler is None:
            return httpx.Response(404, json={"detail": f"no route for {request.method} {request.url.path}"})
        return handler(request)

    # Convenience accessors --------------------------------------------------
    def last(self, method: str, path: str) -> httpx.Request:
        for req in reversed(self.requests):
            if req.method == method.upper() and req.url.path == path:
                return req
        raise AssertionError(f"no recorded {method} {path}")

    def count(self, method: str, path: str) -> int:
        return sum(1 for r in self.requests if r.method == method.upper() and r.url.path == path)


def _fake_jwt(user_id: str, addr: str, exp: int = 9999999999) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": user_id, "addr": addr, "exp": exp}).encode()
    ).decode().rstrip("=")
    return f"h.{payload}.s"


def install_auth(server: MockServer, address: str) -> None:
    """Register the SIWE nonce/verify routes that mint a session for ``address``."""

    @server.route("POST", "/auth/nonce")
    def _nonce(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        addr = body["address"]
        msg = (
            f"umbra wants you to sign in with your Ethereum account:\n{addr}\n\n"
            f"Sign in.\n\nURI: x\nVersion: 1\nChain ID: 1\nNonce: n123\nIssued At: now"
        )
        return httpx.Response(200, json={
            "address": addr, "nonce": "n123", "message": msg,
            "issued_at": 1, "expires_at": 9999999999,
        })

    @server.route("POST", "/auth/verify")
    def _verify(req: httpx.Request) -> httpx.Response:
        from eth_account.messages import encode_defunct
        body = json.loads(req.content)
        recovered = Account.recover_message(
            encode_defunct(text=body["message"]), signature=body["signature"]
        ).lower()
        assert recovered == address.lower(), (recovered, address)
        return httpx.Response(200, json={
            "token": _fake_jwt(address, address), "token_type": "Bearer",
            "expires_at": 9999999999, "user_id": address, "wallet_address": address,
        })


@pytest.fixture
def account():
    """A throwaway Ethereum account for SIWE signing in tests."""
    return Account.create()


@pytest.fixture
def server():
    return MockServer()


@pytest.fixture
def make_client(server, account):
    """Factory: build a sync Client wired to the mock server (auth routes installed)."""
    created: List[Client] = []

    def _make(*, authed: bool = True, **kwargs) -> Client:
        install_auth(server, account.address.lower())
        creds = {"private_key": account.key.hex()} if authed else {}
        client = Client(
            api_url="http://test.local",
            transport=server.transport,
            backoff_factor=0.0,
            backoff_max=0.0,
            **creds,
            **kwargs,
        )
        created.append(client)
        return client

    yield _make
    for c in created:
        c.close()


@pytest.fixture
def fake_jwt():
    return _fake_jwt
