"""Fees tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

FEES = {
    "user_id": "u",
    "next_cursor": "",
    "fees": [
        {
            "entry_id": "f1",
            "trade_id": "t1",
            "user_id": "u",
            "market_id": "m1",
            "market_slug": "btc",
            "role": "MAKER",
            "side": "SELL",
            "fee_rate": "0.01",
            "rebate_rate": "0.01",
            "fee_amount": "0",
            "rebate_amount": "2.40",
            "net_fee": "-2.40",
            "currency": "USDC",
            "seq": 5,
            "ts": 1,
            "timestamp": "2026-01-01T00:00:00Z",
        },
    ],
}

SUMMARY = {
    "user_id": "u",
    "currency": "USDC",
    "total_fees_paid": "1.00",
    "total_rebates_received": "3.40",
    "net_fees": "-2.40",
    "maker_trades": 2,
    "taker_trades": 1,
    "average_fee_per_trade": "1.00",
    "average_rebate_per_trade": "1.70",
}


@pytest.fixture
def client(make_client, server):
    server.json_route("GET", "/user/fees", FEES)
    server.json_route("GET", "/user/fees/summary", SUMMARY)
    server.json_route(
        "GET", "/user/fees/t1", {"trade_id": "t1", "user_id": "u", "entries": FEES["fees"]}
    )
    return make_client()


def test_fee_history(client, server):
    entries = client.get_fee_history(role="maker", sort="-ts")
    assert len(entries) == 1
    assert entries[0].net_fee == Decimal("-2.40")
    assert entries[0].role == "MAKER"
    # Filter is uppercased on the wire.
    assert server.last("GET", "/user/fees").url.params["role"] == "MAKER"


def test_fee_summary_net_earner(client):
    summary = client.get_fee_summary()
    assert summary.net_fees == Decimal("-2.40")
    assert summary.is_net_earner is True
    assert summary.maker_trades == 2


def test_trade_fees(client):
    entries = client.get_trade_fees("t1")
    assert len(entries) == 1
    assert entries[0].trade_id == "t1"
