# UMBRA Python SDK

The official Python SDK for **UMBRA** — an institutional dark-pool ATS for binary
(YES/NO) prediction markets. It wraps authentication, request signing, retries, error
handling, pagination, and WebSocket management so you can focus on strategy.

- **Async-first** with synchronous wrappers (identical surface, zero duplicated logic)
- **Fully typed** models (no raw dicts) — money is `Decimal`, quantities are `int`
- **SIWE auth handled for you** — nonce → sign → JWT → refresh
- **Dark-pool aware** — only the public NBBO is ever exposed, never hidden book depth
- **Production-ready** — exponential-backoff retries, typed exceptions, auto-reconnecting feeds

Requires Python 3.10+.

---

## Installation

```bash
pip install umbra-sdk
```

To sign the Sign-In-with-Ethereum (SIWE) challenge locally with a private key, install the
`wallet` extra (pulls in `eth-account`):

```bash
pip install "umbra-sdk[wallet]"
```

You can skip the extra if you authenticate with a pre-minted session token or your own
signer callback.

---

## Quick start

Place your first trade in a few lines:

```python
from umbra import Client

client = Client(
    api_url="https://api.umbra.exchange",
    private_key="0x...",            # signs the SIWE login locally
)

# Discover markets (public, no auth)
for market in client.get_crypto_markets():
    print(market.slug, market.title, market.status)

# Top-of-book
nbbo = client.get_nbbo("btc-updown-5m")
print(nbbo.best_bid, nbbo.best_ask, nbbo.mid)

# Trade
order = client.place_limit_order(
    market="btc-updown-5m",
    side="BUY", outcome="YES",
    price="0.62", size=1000,
    client_order_id="my-key-1",      # idempotency key
)
print(order.order_id, order.status, order.filled_size)

client.close()
```

Use it as a context manager to close automatically:

```python
with Client(api_url="https://api.umbra.exchange", private_key="0x...") as client:
    print(client.get_markets())
```

### Async

The async client has the **same methods** — just `await` them:

```python
import asyncio
from umbra import AsyncUmbraClient

async def main():
    async with AsyncUmbraClient(api_url="https://api.umbra.exchange", private_key="0x...") as client:
        nbbo = await client.get_nbbo("btc-updown-5m")
        order = await client.place_limit_order(
            market="btc-updown-5m", side="BUY", outcome="YES", price="0.62", size=1000,
        )
        print(order.status)

asyncio.run(main())
```

---

## Authentication

UMBRA uses **Sign-In with Ethereum (SIWE)**. The SDK runs the whole flow — request a
nonce, sign the challenge, exchange it for a JWT, and refresh before expiry — on the first
authenticated call. Public calls (markets, NBBO, trade tape) need no credentials.

Three credential styles:

```python
# 1. Private key — local signing (needs `umbra-sdk[wallet]`)
Client(api_url=URL, private_key="0x...")

# 2. Custom signer — e.g. a hardware wallet / KMS / browser bridge
Client(api_url=URL, wallet_address="0x...", signer=lambda message: my_sign(message))

# 3. Pre-minted token — you obtained a JWT out of band
Client(api_url=URL, token="eyJ...")
```

Force a login (otherwise lazy) and inspect the session:

```python
session = client.authenticate()
print(session.user_id, session.expires_at)
```

> **Security:** never hardcode a private key — load it from an environment variable or a
> secrets manager.

---

## What you can do

### Markets (public)

```python
client.get_markets(category="crypto", status="OPEN", limit=50)
client.get_market("btc-updown-5m")          # by slug or id, enriched with NBBO
client.search_markets("fed cut")
client.get_categories()
client.get_nbbo("btc-updown-5m")            # top-of-book only
client.get_market_orderbook("btc-updown-5m")  # NBBO rendered as a 1-level book
client.get_crypto_markets(); client.get_politics_markets(); client.get_sports_markets()
```

### Orders

```python
client.place_order(market="m1", side="BUY", outcome="YES",
                   order_type="LIMIT", price="0.62", size=1000)
client.place_limit_order(market="m1", side="SELL_NO", price="0.41", size=500, post_only=True)
client.place_market_order(market="m1", side="BUY", outcome="YES", size=250)
client.validate_order(market="m1", side="BUY_YES", price="0.62", size=1000)  # dry-run

client.cancel_order("ord-m1-7")             # market inferred from the id
client.cancel_order_by_client_id("my-key-1")
client.cancel_all_orders(market="m1")
client.modify_order("ord-m1-7", price="0.63", size=800)   # cancel/replace

client.get_order("ord-m1-7")
client.get_orders(limit=250)                # auto-paginates
client.get_open_orders()
client.get_order_history()
```

`side` accepts `"BUY"`/`"SELL"` with `outcome="YES"/"NO"`, or an explicit
`"BUY_YES"`/`"SELL_YES"`/`"BUY_NO"`/`"SELL_NO"`.

### Positions & balances

```python
client.get_positions()                      # signed net_qty, marked uPnL, market value
client.get_position("btc-updown-5m")
client.get_account()                        # trading cash / reserved / available

client.get_wallet_balance()                 # internal trading balance (buying power)
client.get_wallet_assets()                  # live on-chain ETH + USDC
client.get_usdc_balance()                   # live on-chain USDC
```

### Trades & fees

```python
client.get_trades("btc-updown-5m", limit=100)   # public anonymized tape, newest first
client.get_trade("trd-m1-1", market="btc-updown-5m")
client.get_fills(limit=200)                      # your own executions

client.get_fee_history(role="MAKER", limit=500)
client.get_fee_summary()
client.get_trade_fees("trd-m1-1")
```

All money/price fields are `Decimal`; quantities are `int`.

---

## WebSockets

Real-time feeds with automatic reconnect, heartbeat tracking, auth, and subscription
recovery:

```python
ws = client.websocket()

ws.subscribe_nbbo("btc-updown-5m", handler=lambda d: print("nbbo", d["best_bid"], d["best_ask"]))
ws.subscribe_trades(handler=lambda d: print("trade", d["price"], d["quantity"]))   # all markets

# Private feed (requires auth) — one connection, three kinds of update:
ws.subscribe_orders(lambda o: print("order", o["order_id"], o["status"]))
ws.subscribe_positions(lambda p: print("position", p["market_id"], p["net_qty"]))
ws.subscribe_balance(lambda a: print("balance", a["available"]))

# ... do work ...
ws.close()
```

The async client returns an awaitable WebSocket client with the same methods
(`await ws.subscribe_nbbo(...)`).

---

## Error handling

Every error derives from `UmbraError`; raw HTTP errors are never surfaced.

```python
from umbra import (
    UmbraError, AuthenticationError, OrderRejectedError, MarketClosedError,
    InsufficientFundsError, RateLimitError, ValidationError, NotFoundError,
    NetworkError, APIError,
)

try:
    client.place_limit_order(market="m1", side="BUY_YES", price="0.62", size=1000)
except InsufficientFundsError as e:
    print("not enough buying power:", e.validation)
except OrderRejectedError as e:
    print("rejected:", e.reason)
except UmbraError as e:
    print("something went wrong:", e)
```

Transient failures (network errors, `5xx`, `429`) are retried automatically with
exponential backoff. Invalid user requests (`4xx`) are never retried. A non-idempotent
`POST` is only retried when it carries a `client_order_id`.

---

## Configuration

Nothing is hardcoded:

```python
Client(
    api_url="https://api.umbra.exchange",
    ws_url=None,            # defaults to api_url with ws/wss scheme
    timeout=30.0,
    retries=3,
    backoff_factor=0.5,
    backoff_max=10.0,
    debug=True,            # log requests/responses (auth redacted)
)
```

---

## Examples

Runnable scripts live in [`examples/`](examples/): connecting, listing markets, NBBO,
placing limit/market orders, cancelling, positions, fee history, and the NBBO / trade /
private WebSocket feeds. Each reads `UMBRA_API_URL` and `UMBRA_PRIVATE_KEY` from the
environment.

```bash
export UMBRA_API_URL="http://localhost:8000"
export UMBRA_PRIVATE_KEY="0x..."
python examples/place_limit_order.py
```

---

## Development

```bash
pip install -e ".[dev]"
pytest            # offline test suite (mocked transport + a local WS server)
black umbra tests examples
ruff check umbra tests examples
```

## License

MIT
