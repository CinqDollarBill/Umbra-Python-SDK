"""Fetch the NBBO (top-of-book) and the NBBO-only "order book" for a market.

UMBRA is a dark pool — only the best bid/ask is ever exposed, never depth.

    python examples/get_nbbo.py <market-slug-or-id>
"""

import os
import sys

from umbra import Client

market = sys.argv[1] if len(sys.argv) > 1 else "btc-updown-5m"
client = Client(api_url=os.environ.get("UMBRA_API_URL", "http://localhost:8000"))

nbbo = client.get_nbbo(market)
print(f"Market:     {nbbo.market_id}")
print(f"Best bid:   {nbbo.best_bid} x {nbbo.best_bid_size}")
print(f"Best ask:   {nbbo.best_ask} x {nbbo.best_ask_size}")
print(f"Last trade: {nbbo.last_trade_price}")
print(f"Mid:        {nbbo.mid}    Spread: {nbbo.spread}")

book = client.get_market_orderbook(market)
print("\nBook (NBBO-only — at most one level per side):")
print("  bids:", [(str(lvl.price), lvl.size) for lvl in book.bids])
print("  asks:", [(str(lvl.price), lvl.size) for lvl in book.asks])

client.close()
