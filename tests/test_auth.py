"""Authentication (SIWE) tests."""

from __future__ import annotations

import httpx
import pytest

from umbra import AuthenticationError, Client


def test_siwe_signs_and_caches_session(make_client, server, account):
    client = make_client()
    server.json_route(
        "GET",
        "/wallet/balance",
        {
            "user_id": account.address.lower(),
            "cash": "100",
            "reserved_margin": "0",
            "available": "100",
        },
    )

    # First authed call triggers the nonce/verify dance.
    client.get_wallet_balance()
    assert server.count("POST", "/auth/nonce") == 1
    assert server.count("POST", "/auth/verify") == 1
    assert client.user_id == account.address.lower()

    # The bearer token is attached and reused (no second login).
    client.get_wallet_balance()
    assert server.count("POST", "/auth/nonce") == 1
    assert server.last("GET", "/wallet/balance").headers["authorization"].startswith("Bearer ")


def test_preminted_token_skips_siwe(server, fake_jwt):
    token = fake_jwt("user-x", "0xabc", exp=9999999999)
    server.json_route(
        "GET",
        "/wallet/balance",
        {
            "user_id": "user-x",
            "cash": "1",
            "reserved_margin": "0",
            "available": "1",
        },
    )
    client = Client(api_url="http://t", transport=server.transport, token=token, backoff_factor=0.0)
    try:
        client.get_wallet_balance()
        assert server.count("POST", "/auth/nonce") == 0  # no SIWE
        assert client.user_id == "user-x"
        assert server.last("GET", "/wallet/balance").headers["authorization"] == f"Bearer {token}"
    finally:
        client.close()


def test_authenticated_call_without_credentials_raises(make_client, server):
    client = make_client(authed=False)
    with pytest.raises(AuthenticationError):
        client.get_wallet_balance()


def test_401_triggers_single_reauth(make_client, server, account):
    client = make_client()
    state = {"calls": 0}

    @server.route("GET", "/wallet/balance")
    def _bal(req: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(401, json={"detail": "expired"})
        return httpx.Response(
            200,
            json={
                "user_id": account.address.lower(),
                "cash": "5",
                "reserved_margin": "0",
                "available": "5",
            },
        )

    bal = client.get_wallet_balance()
    assert bal.available == __import__("decimal").Decimal("5")
    # One initial login + one re-login after the 401.
    assert server.count("POST", "/auth/verify") == 2
    assert state["calls"] == 2


def test_public_calls_need_no_auth(make_client, server):
    client = make_client(authed=False)
    server.json_route("GET", "/markets", [])
    assert client.get_markets() == []
    assert server.count("POST", "/auth/nonce") == 0
