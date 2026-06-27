"""Trade tape + fills tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from umbra import NotFoundError

MARKETS = [{"market_id": "m1", "title": "BTC up?", "status": "OPEN", "created_seq": 1,
            "created_ts": 1, "category": "crypto", "polymarket_slug": "btc-updown-5m"}]

# REST tape is oldest -> newest.
TAPE = [
    {"trade_id": "t1", "market_id": "m1", "price": "0.60", "quantity": 400,
     "taker_book_side": "BID", "seq": 5, "ts": 1},
    {"trade_id": "t2", "market_id": "m1", "price": "0.61", "quantity": 100,
     "taker_book_side": "ASK", "seq": 6, "ts": 2},
]

FILLS = {"user_id": "u", "next_cursor": "", "fills": [
    {"trade_id": "t1", "market_id": "m1", "price": "0.60", "quantity": 400,
     "side": "BUY_YES", "role": "taker", "fee_or_rebate": "2.40",
     "settlement_status": "PENDING", "seq": 5, "ts": 1},
]}


@pytest.fixture
def client(make_client, server):
    server.json_route("GET", "/markets", MARKETS)
    server.json_route("GET", "/markets/m1/trades", TAPE)
    server.json_route("GET", "/user/fills", FILLS)
    return make_client()


def test_public_tape_newest_first(client):
    trades = client.get_trades("btc-updown-5m")
    assert [t.trade_id for t in trades] == ["t2", "t1"]
    assert trades[0].aggressor_side == "SELL"   # taker_book_side ASK
    assert trades[1].aggressor_side == "BUY"    # taker_book_side BID
    assert trades[1].price == Decimal("0.60")


def test_get_trade_by_id(client):
    t = client.get_trade("t1", market="m1")
    assert t.quantity == 400


def test_get_trade_unknown_raises(client):
    with pytest.raises(NotFoundError):
        client.get_trade("nope", market="m1")


def test_get_fills(client):
    fills = client.get_fills()
    assert len(fills) == 1
    assert fills[0].role == "taker"
    assert fills[0].fee_or_rebate == Decimal("2.40")
    assert fills[0].side == "BUY_YES"
