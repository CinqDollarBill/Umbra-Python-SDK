"""Model parsing tests (no HTTP) — Decimal money, derived fields, both order shapes."""

from __future__ import annotations

from decimal import Decimal

from umbra.models.common import Nbbo, OrderBook
from umbra.models.fee import FeeSummary
from umbra.models.market import Market
from umbra.models.order import Order
from umbra.models.position import Position
from umbra.models.trade import Fill, Trade
from umbra.types import resolve_side


def test_nbbo_parsing_and_derived():
    nbbo = Nbbo.from_api({
        "market_id": "m1", "best_bid": "0.59", "best_bid_size": 500,
        "best_ask": "0.61", "best_ask_size": 400, "last_trade_price": "0.60",
    })
    assert isinstance(nbbo.best_bid, Decimal)
    assert nbbo.mid == Decimal("0.60")
    assert nbbo.spread == Decimal("0.02")


def test_nbbo_empty_side():
    nbbo = Nbbo.from_api({"market_id": "m1", "best_bid": None, "best_ask": "0.61"})
    assert nbbo.best_bid is None
    assert nbbo.mid is None
    assert nbbo.spread is None
    book = OrderBook.from_nbbo(nbbo)
    assert book.bids == []
    assert len(book.asks) == 1


def test_market_slug_resolution_fields():
    m = Market.from_api({
        "market_id": "m1", "title": "Will BTC be Up?!", "status": "OPEN",
        "created_seq": 1, "created_ts": 1, "polymarket_slug": "btc-up",
        "kalshi_slug": "KX1",
    })
    assert m.slug == "btc-up"
    assert "btc-up" in m.slugs and "KX1" in m.slugs and "m1" in m.slugs
    # Title-derived slug is also matchable.
    assert "will-btc-be-up" in m.slugs


def test_order_from_record():
    o = Order.from_api({
        "order_id": "ord-m1-7", "market_id": "m1", "user_id": "u", "side": "SELL_NO",
        "book_side": "BID", "order_type": "LIMIT", "tif": "GTC", "limit_price": "0.35",
        "quantity": 1000, "filled_quantity": 400, "remaining_quantity": 600,
        "status": "PARTIALLY_FILLED", "seq": 7, "ts": 9,
    })
    assert o.price == Decimal("0.35")
    assert o.outcome == "NO" and o.action == "SELL"
    assert o.remaining_size == 600
    assert o.is_open and not o.is_terminal


def test_order_from_submit_computes_fills():
    result = {
        "order_id": "ord-m1-5", "market_id": "m1", "status": "FILLED", "reason": None,
        "fills": [
            {"trade_id": "t1", "price": "0.60", "quantity": 600, "net_fee": "3.6", "seq": 5, "ts": 1},
            {"trade_id": "t2", "price": "0.61", "quantity": 400, "net_fee": "2.4", "seq": 6, "ts": 2},
        ],
    }
    o = Order.from_submit(result, side="BUY_YES", order_type="LIMIT", time_in_force="IOC",
                          price=Decimal("0.62"), size=1000)
    assert o.filled_size == 1000
    assert o.remaining_size == 0
    assert len(o.fills) == 2
    assert all(isinstance(f, Fill) for f in o.fills)
    assert o.fills[0].price == Decimal("0.60")


def test_position_market_value_and_outcome():
    long = Position.from_api({"market_id": "m1", "net_qty": 1000, "avg_entry_price": "0.6",
                              "realized_pnl": "0", "mark_price": "0.65"})
    assert long.outcome == "YES"
    assert long.market_value == Decimal("0.65") * 1000
    flat = Position.from_api({"market_id": "m2", "net_qty": 0, "avg_entry_price": "0",
                              "realized_pnl": "0"})
    assert flat.outcome is None
    assert flat.market_value is None


def test_trade_aggressor():
    assert Trade.from_api({"trade_id": "t", "market_id": "m", "price": "0.6", "quantity": 1,
                           "taker_book_side": "BID", "seq": 1, "ts": 1}).aggressor_side == "BUY"
    assert Trade.from_api({"trade_id": "t", "market_id": "m", "price": "0.6", "quantity": 1,
                           "taker_book_side": "ASK", "seq": 1, "ts": 1}).aggressor_side == "SELL"


def test_fee_summary_net_earner():
    s = FeeSummary.from_api({"user_id": "u", "currency": "USDC", "total_fees_paid": "1",
                             "total_rebates_received": "3", "net_fees": "-2",
                             "maker_trades": 1, "taker_trades": 1,
                             "average_fee_per_trade": "1", "average_rebate_per_trade": "1.5"})
    assert s.is_net_earner is True


def test_resolve_side_variants():
    assert resolve_side("buy", "yes").value == "BUY_YES"
    assert resolve_side("SELL", "NO").value == "SELL_NO"
    assert resolve_side("BUY_NO").value == "BUY_NO"
    assert resolve_side("bid", "yes").value == "BUY_YES"


def test_resolve_side_invalid():
    import pytest
    with pytest.raises(ValueError):
        resolve_side("sideways", "yes")
    with pytest.raises(ValueError):
        resolve_side("buy", "maybe")
