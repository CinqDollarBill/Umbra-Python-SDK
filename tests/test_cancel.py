"""Order cancellation tests."""

from __future__ import annotations

import json

import httpx
import pytest

from umbra import NotFoundError, OrderRejectedError

MARKETS = [
    {
        "market_id": "m1",
        "title": "BTC up?",
        "status": "OPEN",
        "created_seq": 1,
        "created_ts": 1,
        "category": "crypto",
        "polymarket_slug": "btc-updown-5m",
    }
]


def _cancel_ok(req: httpx.Request) -> httpx.Response:
    body = json.loads(req.content)
    return httpx.Response(
        200,
        json={
            "order_id": body["order_id"],
            "market_id": body["market_id"],
            "status": "CANCELED",
            "reason": None,
            "nbbo": {
                "market_id": "m1",
                "best_bid": None,
                "best_bid_size": 0,
                "best_ask": None,
                "best_ask_size": 0,
                "last_trade_price": None,
            },
        },
    )


@pytest.fixture
def client(make_client, server):
    server.json_route("GET", "/markets", MARKETS)
    return make_client()


def test_cancel_infers_market_from_order_id(client, server):
    server.route("POST", "/cancel_order")(_cancel_ok)
    res = client.cancel_order("ord-m1-7")
    body = json.loads(server.last("POST", "/cancel_order").content)
    assert body["market_id"] == "m1"
    assert body["order_id"] == "ord-m1-7"
    assert res.status == "CANCELED"


def test_cancel_rejected_raises(client, server):
    @server.route("POST", "/cancel_order")
    def _rej(req):
        return httpx.Response(
            200,
            json={
                "order_id": "ord-m1-7",
                "market_id": "m1",
                "status": "REJECTED",
                "reason": "UNKNOWN_OR_INACTIVE",
                "nbbo": {
                    "market_id": "m1",
                    "best_bid": None,
                    "best_bid_size": 0,
                    "best_ask": None,
                    "best_ask_size": 0,
                    "last_trade_price": None,
                },
            },
        )

    with pytest.raises(OrderRejectedError) as exc:
        client.cancel_order("ord-m1-7")
    assert exc.value.reason == "UNKNOWN_OR_INACTIVE"


def test_cancel_by_client_id(client, server):
    # Place an order with a client id so the SDK can resolve it on cancel.
    server.json_route(
        "POST",
        "/orders",
        {
            "accepted": True,
            "reason": None,
            "validation": {
                "valid": True,
                "reason": None,
                "market_id": "m1",
                "wallet_balance": "1",
                "required_collateral": "0",
                "available_after_trade": "1",
            },
            "order": {
                "order_id": "ord-m1-9",
                "market_id": "m1",
                "user_id": "u",
                "status": "OPEN",
                "reason": None,
                "fills": [],
                "fees": {
                    "fill_count": 0,
                    "total_fee": "0",
                    "total_rebate": "0",
                    "total_net_fee": "0",
                },
                "nbbo": {
                    "market_id": "m1",
                    "best_bid": None,
                    "best_bid_size": 0,
                    "best_ask": None,
                    "best_ask_size": 0,
                    "last_trade_price": None,
                },
            },
        },
    )
    server.route("POST", "/cancel_order")(_cancel_ok)

    client.place_limit_order(
        market="m1", side="BUY_YES", price="0.5", size=10, client_order_id="abc"
    )
    res = client.cancel_order_by_client_id("abc")
    body = json.loads(server.last("POST", "/cancel_order").content)
    assert body["order_id"] == "ord-m1-9"
    assert res.status == "CANCELED"


def test_cancel_by_unknown_client_id_raises(client):
    with pytest.raises(NotFoundError):
        client.cancel_order_by_client_id("never-placed")


def test_cancel_all(client, server):
    server.json_route(
        "GET",
        "/user/orders",
        {
            "user_id": "u",
            "next_cursor": "",
            "orders": [
                {
                    "order_id": "ord-m1-1",
                    "market_id": "m1",
                    "user_id": "u",
                    "side": "BUY_YES",
                    "book_side": "BID",
                    "order_type": "LIMIT",
                    "tif": "GTC",
                    "limit_price": "0.5",
                    "quantity": 10,
                    "filled_quantity": 0,
                    "remaining_quantity": 10,
                    "status": "OPEN",
                    "seq": 1,
                    "ts": 1,
                },
                {
                    "order_id": "ord-m1-2",
                    "market_id": "m1",
                    "user_id": "u",
                    "side": "SELL_YES",
                    "book_side": "ASK",
                    "order_type": "LIMIT",
                    "tif": "GTC",
                    "limit_price": "0.7",
                    "quantity": 10,
                    "filled_quantity": 0,
                    "remaining_quantity": 10,
                    "status": "OPEN",
                    "seq": 2,
                    "ts": 2,
                },
            ],
        },
    )
    server.route("POST", "/cancel_order")(_cancel_ok)
    canceled = client.cancel_all_orders()
    assert {o.order_id for o in canceled} == {"ord-m1-1", "ord-m1-2"}
    assert server.count("POST", "/cancel_order") == 2
