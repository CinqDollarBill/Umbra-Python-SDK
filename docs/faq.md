# FAQ

### How do I authenticate without installing `eth-account`?

Use a **pre-minted token** (`Client(api_url=URL, token="eyJ...")`) or a **custom signer**
(`Client(api_url=URL, wallet_address="0x...", signer=my_sign)`). The `eth-account`
dependency (via `pip install "umbra-sdk[wallet]"`) is only needed for local `private_key`
signing.

### Why are prices `Decimal` and not `float`?

The exchange returns money/prices as decimal strings to avoid binary-float drift. The SDK
keeps them as `decimal.Decimal`. Do your arithmetic in `Decimal` and only convert for
display.

### Can I see the full order book?

No. UMBRA is a dark pool — only the NBBO (best bid/ask + size + last trade) is published.
`get_market_orderbook()` returns the NBBO in book shape with at most one level per side.

### Sync or async — which should I use?

Both expose the same methods. Use `Client` (sync) for scripts and simple bots; use
`AsyncUmbraClient` for high-concurrency strategies or async frameworks. The sync client
runs the async core on a background event loop, so there is no behavioral difference.

### Does `place_order` return immediately filled trades?

Yes. The returned `Order` includes any `fills` generated at submission, plus
`filled_size`/`remaining_size`/`status`. You don't need to poll to learn an order's
immediate executions.

### How do `client_order_id`s work?

Pass one to `place_order` as an idempotency key. The SDK also tracks it locally so you can
`cancel_order_by_client_id(...)` and see it echoed back on the returned `Order`. Passing one
also makes a `POST` safe to retry automatically.

### How is `modify_order` implemented?

As an explicit cancel/replace — the venue has no in-place amend. It cancels the existing
order, then places a new one with your overrides, and returns the new order. If the cancel
fails (already filled), the rejection propagates and no new order is placed.

### What's the difference between the balance methods?

- `get_wallet_balance()` — internal **trading** balance (cash / reserved / available); your
  buying power on the venue.
- `get_wallet_assets()` — live **on-chain** ETH + USDC.
- `get_usdc_balance()` — live **on-chain** USDC (the just-in-time buying power that gates
  order admission).

### Do WebSocket subscriptions reconnect on their own?

Yes — with exponential backoff, and they re-establish the same subscription. A fatal
`error` frame (e.g. `UNKNOWN_MARKET`) is the exception: that feed stops and does not
reconnect.

### Are my WebSocket handlers called on the main thread?

In the sync client they run on the SDK's background event-loop thread. Keep them quick and
thread-safe, or use `ws.listen()` to pull frames on your own thread.

### How do I turn on debug logging?

Construct the client with `debug=True`. The SDK logs requests/responses (auth headers
redacted) on the `umbra` logger.

### Which Python versions are supported?

Python 3.10 and newer.
