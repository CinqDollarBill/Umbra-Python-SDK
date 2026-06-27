# UMBRA Python SDK — Documentation

The official Python SDK for **UMBRA**, an institutional dark-pool ATS for binary (YES/NO)
prediction markets. It abstracts away authentication, request signing, retries, error
handling, pagination, and WebSocket management.

## Contents

1. [Installation](installation.md)
2. [Authentication](authentication.md)
3. [Quick Start](quickstart.md)
4. [Market Examples](markets.md)
5. [Order Examples](orders.md)
6. [WebSocket Examples](websockets.md)
7. [Error Handling](errors.md)
8. [FAQ](faq.md)

## Design at a glance

- **Async-first, sync-friendly.** `AsyncUmbraClient` is the async core; `Client`
  (`UmbraClient`) is a synchronous facade that runs the same logic on a background event
  loop. Both expose an identical, flat method surface.
- **Typed models, not dicts.** Responses parse into dataclasses (`Market`, `Order`,
  `Position`, `Nbbo`, `Fill`, `FeeEntry`, ...). Money/prices are `decimal.Decimal`;
  quantities are `int`. Every model keeps the original payload on `.raw`.
- **Dark-pool aware.** Only the public NBBO (best bid/ask + size + last trade) is exposed.
  There is no hidden order book; `get_market_orderbook()` returns the NBBO in book shape
  with at most one level per side.
- **Resilient.** Transient failures are retried with exponential backoff; WebSocket feeds
  reconnect automatically and recover their subscriptions.

## A complete first program

```python
from umbra import Client

with Client(api_url="https://api.umbra.exchange", private_key="0x...") as client:
    market = client.get_market("btc-updown-5m")
    print(market.title, "->", market.best_bid, "/", market.best_ask)

    order = client.place_limit_order(
        market=market.slug, side="BUY", outcome="YES", price="0.62", size=1000,
    )
    print(order.order_id, order.status)

    for position in client.get_positions():
        print(position.market_id, position.net_qty, position.unrealized_pnl)
```
