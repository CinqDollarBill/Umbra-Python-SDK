# Market Examples

Market discovery and market data are **public** — no authentication required.

## List and filter

```python
client.get_markets()                                  # everything
client.get_markets(category="crypto")                 # by category
client.get_markets(status="OPEN", limit=50)           # by status, capped
```

Each item is a `Market`:

```python
m = client.get_markets()[0]
m.market_id      # internal id
m.slug           # human-readable slug (external slug if present, else derived)
m.title
m.category       # "crypto" | "politics" | "sports" | ...
m.status         # "OPEN" | "HALTED" | "SETTLED" | ...
m.is_open        # convenience flag
m.tokens         # the synthetic YES / NO tokens
```

## Discovery helpers

```python
client.get_crypto_markets()
client.get_politics_markets()
client.get_sports_markets()
client.get_categories()      # -> ["crypto", "politics", "sports"]
```

## Look up one market

`get_market` accepts a slug **or** an id, and enriches the result with the NBBO:

```python
m = client.get_market("btc-updown-5m")
print(m.best_bid, m.best_ask, m.last_trade_price)

m = client.get_market("m1", with_nbbo=False)   # skip the extra NBBO fetch
```

A missing market raises `NotFoundError`.

## Search

```python
for m in client.search_markets("fed cut"):
    print(m.slug, m.title)
```

## Market data — NBBO only

UMBRA is a dark pool: the only market-data surface is the National Best Bid/Offer.

```python
nbbo = client.get_nbbo("btc-updown-5m")
nbbo.best_bid          # Decimal | None
nbbo.best_bid_size     # int (aggregate size at exactly the best level)
nbbo.best_ask, nbbo.best_ask_size
nbbo.last_trade_price  # Decimal | None
nbbo.mid               # Decimal | None
nbbo.spread            # Decimal | None
```

`get_market_orderbook` returns the same data in a familiar book shape — but with **at most
one level per side** (never depth):

```python
book = client.get_market_orderbook("btc-updown-5m")
book.bids   # [] or [BookLevel(price=..., size=...)]
book.asks   # [] or [BookLevel(price=..., size=...)]
```

## Prices are decimals

All prices are `decimal.Decimal` (parsed from the API's decimal strings). Never coerce to
`float` for math:

```python
from decimal import Decimal
edge = Decimal("0.65") - nbbo.best_ask
```
