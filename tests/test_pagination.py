"""Cursor pagination tests."""

from __future__ import annotations

import asyncio

import httpx

from umbra.utils.pagination import collect_pages

MARKETS = [
    {
        "market_id": "m1",
        "title": "BTC",
        "status": "OPEN",
        "created_seq": 1,
        "created_ts": 1,
        "category": "crypto",
        "polymarket_slug": "btc",
    }
]


def _order(seq):
    return {
        "order_id": f"ord-m1-{seq}",
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
        "seq": seq,
        "ts": seq,
    }


def test_collect_pages_walks_cursors():
    pages = {
        "": (["a", "b"], "c1"),
        "c1": (["c", "d"], "c2"),
        "c2": (["e"], ""),
    }

    async def fetch(cursor, page_size):
        return pages[cursor]

    out = asyncio.run(collect_pages(fetch, None))
    assert out == ["a", "b", "c", "d", "e"]


def test_collect_pages_respects_limit():
    async def fetch(cursor, page_size):
        # Always returns a full page and a next cursor.
        start = int(cursor or "0")
        items = list(range(start, start + page_size))
        return items, str(start + page_size)

    out = asyncio.run(collect_pages(fetch, 25))
    assert out == list(range(25))


def test_get_orders_auto_paginates(make_client, server):
    client = make_client()
    server.json_route("GET", "/markets", MARKETS)

    @server.route("GET", "/user/orders")
    def _orders(req: httpx.Request):
        cursor = req.url.params.get("cursor", "")
        if cursor == "":
            return httpx.Response(
                200, json={"user_id": "u", "next_cursor": "p2", "orders": [_order(1), _order(2)]}
            )
        return httpx.Response(200, json={"user_id": "u", "next_cursor": "", "orders": [_order(3)]})

    orders = client.get_orders(limit=None)
    assert [o.order_id for o in orders] == ["ord-m1-1", "ord-m1-2", "ord-m1-3"]
    assert server.count("GET", "/user/orders") == 2


def test_get_orders_limit_slices(make_client, server):
    client = make_client()
    server.json_route("GET", "/markets", MARKETS)

    @server.route("GET", "/user/orders")
    def _orders(req: httpx.Request):
        return httpx.Response(
            200,
            json={
                "user_id": "u",
                "next_cursor": "more",
                "orders": [_order(1), _order(2), _order(3)],
            },
        )

    orders = client.get_orders(limit=2)
    assert len(orders) == 2
