"""Positions tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

MARKETS = [{"market_id": "m1", "title": "BTC up?", "status": "OPEN", "created_seq": 1,
            "created_ts": 1, "category": "crypto", "polymarket_slug": "btc-updown-5m"}]

SNAPSHOT = {
    "positions": [
        {"user_id": "u", "market_id": "m1", "net_qty": 1000, "avg_entry_price": "0.60",
         "realized_pnl": "0", "fees_paid": "6", "rebates_received": "0",
         "mark_price": "0.64", "unrealized_pnl": "40.0"},
        {"user_id": "u", "market_id": "m2", "net_qty": -500, "avg_entry_price": "0.30",
         "realized_pnl": "5", "fees_paid": "1", "rebates_received": "0",
         "mark_price": "0.28", "unrealized_pnl": "10.0"},
    ],
    "account": {"user_id": "u", "cash": "1000", "reserved_margin": "200", "available": "800"},
}


@pytest.fixture
def client(make_client, server):
    server.json_route("GET", "/markets", MARKETS)
    server.json_route("GET", "/user/positions", SNAPSHOT)
    return make_client()


def test_get_positions(client):
    positions = client.get_positions()
    assert len(positions) == 2
    p1 = positions[0]
    assert p1.net_qty == 1000
    assert p1.quantity == 1000
    assert p1.outcome == "YES"
    assert p1.average_price == Decimal("0.60")
    assert p1.unrealized_pnl == Decimal("40.0")
    assert p1.market_value == Decimal("0.64") * 1000


def test_short_position_outcome(client):
    short = client.get_positions()[1]
    assert short.outcome == "NO"
    assert short.quantity == 500
    assert short.market_value == Decimal("0.28") * -500


def test_get_position_by_slug(client):
    p = client.get_position("btc-updown-5m")
    assert p is not None and p.market_id == "m1"


def test_get_account(client):
    acct = client.get_account()
    assert acct.available == Decimal("800")
    assert acct.reserved_margin == Decimal("200")
