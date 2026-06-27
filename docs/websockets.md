# WebSocket Examples

The SDK manages a connection per feed with automatic **reconnect** (exponential backoff),
**heartbeat** liveness, **authentication** (for the private feed), and **subscription
recovery**.

```python
ws = client.websocket()
```

## Public feeds (no auth)

Pass a market (slug or id) for one market, or omit it for the all-markets stream.

```python
ws.subscribe_nbbo("btc-updown-5m", handler=lambda d: print("nbbo", d["best_bid"], d["best_ask"]))
ws.subscribe_trades(handler=lambda d: print("trade", d["price"], d["quantity"]))  # all markets
ws.subscribe_status("btc-updown-5m", handler=lambda d: print("status", d["new_status"]))
```

Channel handlers receive the inner payload (the NBBO dict, the print dict, ...).

## Private feed (auth required)

The single `/ws/user/{user_id}` connection multiplexes order, position, and balance
updates. The convenience methods register a handler for one kind each and share one
connection:

```python
ws.subscribe_orders(lambda o: print("order", o["order_id"], o["status"]))
ws.subscribe_positions(lambda p: print("position", p["market_id"], p["net_qty"]))
ws.subscribe_balance(lambda a: print("balance", a["available"]))

# Or get every private frame on one handler:
ws.subscribe_user(lambda data: print(data["kind"], data))
```

## Lifecycle events

Register global handlers for non-data frames:

```python
ws.on("heartbeat", lambda _: print("alive"))
ws.on("error", lambda frame: print("feed error:", frame["detail"]))
```

An `error` frame (e.g. `UNKNOWN_MARKET`) is fatal for that feed — it will not reconnect.

## Pull frames instead of callbacks

```python
for frame in ws.listen():        # blocking generator of {"type", "data"}
    print(frame)
```

## Closing

```python
ws.close()        # closes every feed
```

## Async usage

The async client's WebSocket has the same methods, all awaitable:

```python
async with AsyncUmbraClient(api_url=URL, private_key=KEY) as client:
    ws = client.websocket()
    await ws.subscribe_nbbo("btc-updown-5m", handler=on_nbbo)
    async for frame in ws.messages():
        ...
    await ws.close()
```

## Notes

- **Seed from REST.** The trade tape sends no backlog on connect — backfill with
  `client.get_trades(market)` first, then subscribe.
- **Sync handlers run on the SDK's background loop thread.** Keep them quick and
  thread-safe (e.g. push to a `queue.Queue`), or use `listen()` to consume on your own
  thread.
- Handlers may be plain functions or coroutines.
