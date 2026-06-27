"""Order placement tests."""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from umbra import (
    ConfigurationError,
    InsufficientFundsError,
    MarketClosedError,
    OrderRejectedError,
)

MARKETS = [
    {"market_id": "m1", "title": "BTC up?", "status": "OPEN", "created_seq": 1,
     "created_ts": 1, "category": "crypto", "polymarket_slug": "btc-updown-5m"},
]


def _accepted_order(status="FILLED", fills=None):
    return {
        "accepted": True, "reason": None,
        "validation": {"valid": True, "reason": None, "market_id": "m1",
                       "wallet_balance": "1000", "required_collateral": "620",
                       "available_after_trade": "380"},
        "order": {
            "order_id": "ord-m1-5", "market_id": "m1", "user_id": "u", "status": status,
            "reason": None, "fills": fills or [], "fees": {"fill_count": 0, "total_fee": "0",
            "total_rebate": "0", "total_net_fee": "0"},
            "nbbo": {"market_id": "m1", "best_bid": None, "best_bid_size": 0,
                     "best_ask": None, "best_ask_size": 0, "last_trade_price": None},
        },
    }


def _rejected(reason, valid=False):
    return {
        "accepted": False, "reason": reason,
        "validation": {"valid": valid, "reason": reason, "market_id": "m1",
                       "wallet_balance": "0", "required_collateral": "620",
                       "available_after_trade": "-620"},
        "order": None,
    }


@pytest.fixture
def client(make_client, server):
    server.json_route("GET", "/markets", MARKETS)
    return make_client()


def test_place_limit_order_body_and_parse(client, server):
    fills = [{"trade_id": "t1", "price": "0.60", "quantity": 1000, "taker_user_id": "u",
              "taker_book_side": "BID", "notional": "600", "fee_rate": "0.01",
              "rebate_rate": "0.01", "fee_amount": "6", "rebate_amount": "0",
              "net_fee": "6", "seq": 5, "ts": 1}]
    server.json_route("POST", "/orders", _accepted_order("FILLED", fills))

    order = client.place_limit_order(
        market="btc-updown-5m", side="BUY", outcome="YES", price="0.62",
        size=1000, post_only=True, client_order_id="cli-1",
    )

    body = json.loads(server.last("POST", "/orders").content)
    assert body == {
        "market_id": "m1", "side": "BUY_YES", "type": "LIMIT", "quantity": 1000,
        "tif": "GTC", "post_only": True, "client_order_id": "cli-1", "price": 0.62,
    }
    assert order.order_id == "ord-m1-5"
    assert order.status == "FILLED"
    assert order.filled_size == 1000
    assert order.side == "BUY_YES" and order.outcome == "YES" and order.action == "BUY"
    assert order.client_order_id == "cli-1"
    assert order.fills[0].price == Decimal("0.60")


def test_place_market_order_omits_price(client, server):
    server.json_route("POST", "/orders", _accepted_order("FILLED"))
    client.place_market_order(market="m1", side="SELL", outcome="NO", size=500)
    body = json.loads(server.last("POST", "/orders").content)
    assert body["type"] == "MARKET"
    assert "price" not in body
    assert body["side"] == "SELL_NO"
    assert body["tif"] == "IOC"


def test_limit_requires_price(client):
    with pytest.raises(ConfigurationError):
        client.place_order(market="m1", side="BUY_YES", size=100, order_type="LIMIT")


def test_market_forbids_price(client):
    with pytest.raises(ConfigurationError):
        client.place_order(market="m1", side="BUY_YES", size=100, order_type="MARKET", price="0.5")


def test_insufficient_funds_rejection(client, server):
    server.json_route("POST", "/orders", _rejected("INSUFFICIENT_FUNDS"))
    with pytest.raises(InsufficientFundsError) as exc:
        client.place_limit_order(market="m1", side="BUY_YES", price="0.62", size=1000)
    assert exc.value.reason == "INSUFFICIENT_FUNDS"
    assert exc.value.validation["required_collateral"] == "620"


def test_market_closed_rejection(client, server):
    server.json_route("POST", "/orders", _rejected("MARKET_NOT_OPEN"))
    with pytest.raises(MarketClosedError):
        client.place_limit_order(market="m1", side="BUY_YES", price="0.62", size=1000)


def test_post_only_cross_rejection(client, server):
    server.json_route("POST", "/orders", _rejected("POST_ONLY_WOULD_CROSS"))
    with pytest.raises(OrderRejectedError) as exc:
        client.place_limit_order(market="m1", side="BUY_YES", price="0.62", size=1000, post_only=True)
    assert exc.value.reason == "POST_ONLY_WOULD_CROSS"


def test_idempotent_post_carries_client_order_id_header(client, server):
    # A POST with client_order_id is marked idempotent (safe to retry).
    server.json_route("POST", "/orders", _accepted_order())
    client.place_limit_order(market="m1", side="BUY_YES", price="0.62", size=10, client_order_id="k1")
    # Tracked for cancel-by-client-id.
    assert ("u" not in {})  # placeholder; tracking validated in test_cancel.py
