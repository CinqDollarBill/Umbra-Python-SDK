"""Retry / backoff / error-mapping tests."""

from __future__ import annotations

import json

import httpx
import pytest

from umbra import APIError, NetworkError, NotFoundError, ValidationError

MARKETS = [{"market_id": "m1", "title": "BTC", "status": "OPEN", "created_seq": 1,
            "created_ts": 1, "category": "crypto", "polymarket_slug": "btc"}]


def test_get_retries_on_5xx_then_succeeds(make_client, server):
    client = make_client(authed=False, retries=3)
    state = {"n": 0}

    @server.route("GET", "/markets")
    def _m(req):
        state["n"] += 1
        if state["n"] < 3:
            return httpx.Response(503, json={"detail": "unavailable"})
        return httpx.Response(200, json=MARKETS)

    assert len(client.get_markets()) == 1
    assert state["n"] == 3  # 2 failures + 1 success


def test_get_5xx_exhausts_and_raises(make_client, server):
    client = make_client(authed=False, retries=2)

    @server.route("GET", "/markets")
    def _m(req):
        return httpx.Response(503, json={"detail": "down"})

    with pytest.raises(APIError) as exc:
        client.get_markets()
    assert exc.value.status_code == 503
    assert server.count("GET", "/markets") == 3  # 1 + 2 retries


def test_4xx_not_retried(make_client, server):
    client = make_client(authed=False, retries=3)

    @server.route("GET", "/markets")
    def _m(req):
        return httpx.Response(404, json={"detail": "MARKET_NOT_FOUND"})

    with pytest.raises(NotFoundError):
        client.get_markets()
    assert server.count("GET", "/markets") == 1  # never retried


def test_429_retried_then_succeeds(make_client, server):
    client = make_client(authed=False, retries=3)
    state = {"n": 0}

    @server.route("GET", "/markets")
    def _m(req):
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, json={"detail": "slow down"})
        return httpx.Response(200, json=MARKETS)

    client.get_markets()
    assert state["n"] == 2


def test_network_error_retried_then_raises(make_client, server):
    client = make_client(authed=False, retries=2)

    @server.route("GET", "/markets")
    def _m(req):
        raise httpx.ConnectError("boom", request=req)

    with pytest.raises(NetworkError):
        client.get_markets()
    assert server.count("GET", "/markets") == 3  # 1 + 2 retries (connect errors are safe)


def test_validation_error_surfaces_detail(make_client, server):
    client = make_client(authed=False)

    @server.route("GET", "/markets")
    def _m(req):
        return httpx.Response(422, json={"detail": [
            {"loc": ["query", "limit"], "msg": "value is not a valid integer", "type": "int"}
        ]})

    with pytest.raises(ValidationError) as exc:
        client.get_markets()
    assert "not a valid integer" in str(exc.value)
    assert exc.value.errors


def test_post_without_client_order_id_not_retried_on_5xx(make_client, server):
    client = make_client(retries=3)  # authed
    server.json_route("GET", "/markets", MARKETS)

    @server.route("POST", "/orders")
    def _o(req):
        return httpx.Response(503, json={"detail": "down"})

    with pytest.raises(APIError):
        client.place_limit_order(market="m1", side="BUY_YES", price="0.5", size=10)
    # Non-idempotent POST (no client_order_id): tried exactly once.
    assert server.count("POST", "/orders") == 1


def test_post_with_client_order_id_is_retried_on_5xx(make_client, server):
    client = make_client(retries=2)
    server.json_route("GET", "/markets", MARKETS)

    @server.route("POST", "/orders")
    def _o(req):
        return httpx.Response(503, json={"detail": "down"})

    with pytest.raises(APIError):
        client.place_limit_order(market="m1", side="BUY_YES", price="0.5", size=10,
                                 client_order_id="idem-1")
    assert server.count("POST", "/orders") == 3  # idempotency key -> safe to retry
