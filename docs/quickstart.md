# Quick Start

## Install

```bash
pip install "umbra-sdk[wallet]"
```

## Connect

```python
import os
from umbra import Client

client = Client(
    api_url=os.environ["UMBRA_API_URL"],         # e.g. https://api.umbra.exchange
    private_key=os.environ["UMBRA_PRIVATE_KEY"],
)
```

## Discover a market

```python
markets = client.get_crypto_markets()
market = markets[0]
print(market.slug, market.title, market.status)

nbbo = client.get_nbbo(market.slug)
print("bid", nbbo.best_bid, "ask", nbbo.best_ask, "mid", nbbo.mid)
```

## Place an order

```python
order = client.place_limit_order(
    market=market.slug,
    side="BUY", outcome="YES",
    price="0.62", size=1000,
    client_order_id="quickstart-1",   # idempotency key
)
print(order.order_id, order.status, "filled", order.filled_size)
```

## Check positions and balance

```python
for p in client.get_positions():
    print(p.market_id, p.net_qty, p.unrealized_pnl, p.market_value)

print(client.get_wallet_balance().available)
```

## Cancel

```python
client.cancel_order_by_client_id("quickstart-1")
# or client.cancel_order(order.order_id)
# or client.cancel_all_orders()
```

## Stream live data

```python
ws = client.websocket()
ws.subscribe_nbbo(market.slug, handler=lambda d: print("nbbo", d))
ws.subscribe_orders(lambda o: print("order", o["order_id"], o["status"]))
# ... keep your program alive ...
ws.close()
```

## Clean up

```python
client.close()
```

Or use the client as a context manager so it closes automatically:

```python
with Client(api_url=URL, private_key=KEY) as client:
    ...
```

## Async equivalent

```python
import asyncio
from umbra import AsyncUmbraClient

async def main():
    async with AsyncUmbraClient(api_url=URL, private_key=KEY) as client:
        print(await client.get_nbbo("btc-updown-5m"))

asyncio.run(main())
```
