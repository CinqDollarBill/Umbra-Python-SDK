"""Market discovery + market-data tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from umbra import NotFoundError

MARKETS = [
    {"market_id": "m1", "title": "Will BTC be up?", "status": "OPEN", "outcome": None,
     "created_seq": 1, "created_ts": 111, "category": "crypto", "polymarket_slug": "btc-updown-5m",
     "kalshi_slug": "KXBTC-1"},
    {"market_id": "m2", "title": "Fed cut by Sept?", "status": "OPEN", "outcome": None,
     "created_seq": 2, "created_ts": 112, "category": "politics", "polymarket_slug": "fed-cut"},
    {"market_id": "m3", "title": "Lakers win?", "status": "SETTLED", "outcome": 1,
     "created_seq": 3, "created_ts": 113, "category": "sports", "polymarket_slug": "lakers-win"},
]


@pytest.fixture
def client(make_client, server):
    server.json_route("GET", "/markets", MARKETS)
    server.json_route("GET", "/markets/m1/nbbo", {
        "market_id": "m1", "best_bid": "0.59", "best_bid_size": 500,
        "best_ask": "0.61", "best_ask_size": 400, "last_trade_price": "0.60",
    })
    return make_client(authed=False)


def test_get_markets_and_filters(client):
    assert len(client.get_markets()) == 3
    assert [m.market_id for m in client.get_markets(category="crypto")] == ["m1"]
    assert [m.market_id for m in client.get_markets(status="SETTLED")] == ["m3"]
    assert len(client.get_markets(limit=2)) == 2


def test_discovery_helpers(client):
    assert client.get_crypto_markets()[0].slug == "btc-updown-5m"
    assert client.get_politics_markets()[0].slug == "fed-cut"
    assert client.get_sports_markets()[0].slug == "lakers-win"


def test_categories(client):
    assert client.get_categories() == ["crypto", "politics", "sports"]


def test_search(client):
    assert [m.market_id for m in client.search_markets("fed")] == ["m2"]
    assert [m.market_id for m in client.search_markets("WIN")] == ["m3"]
    assert client.search_markets("nope") == []


def test_get_market_by_slug_and_id_with_nbbo(client):
    by_slug = client.get_market("btc-updown-5m")
    by_id = client.get_market("m1")
    by_kalshi = client.get_market("KXBTC-1")
    assert by_slug.market_id == by_id.market_id == by_kalshi.market_id == "m1"
    assert by_slug.best_bid == Decimal("0.59")
    assert by_slug.best_ask == Decimal("0.61")


def test_get_market_unknown_raises(client):
    with pytest.raises(NotFoundError):
        client.get_market("does-not-exist")


def test_nbbo_and_orderbook(client):
    nbbo = client.get_nbbo("m1")
    assert nbbo.mid == Decimal("0.60")
    assert nbbo.spread == Decimal("0.02")
    book = client.get_market_orderbook("m1")
    assert len(book.bids) == 1 and len(book.asks) == 1  # dark pool: NBBO only
    assert book.bids[0].price == Decimal("0.59")
    assert book.bids[0].size == 500


def test_market_is_open_flags(client):
    assert client.get_market("m1").is_open is True
    assert client.get_market("lakers-win", with_nbbo=False).is_settled is True
