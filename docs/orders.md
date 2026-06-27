# Order Examples

All order operations require authentication.

## Sides

A side is `BUY`/`SELL` of a `YES`/`NO` token. Express it either way:

```python
# action + outcome
client.place_order(market="m1", side="BUY", outcome="YES", order_type="LIMIT", price="0.62", size=1000)

# explicit four-way side
client.place_order(market="m1", side="SELL_NO", order_type="LIMIT", price="0.41", size=500)
```

Valid explicit sides: `BUY_YES`, `SELL_YES`, `BUY_NO`, `SELL_NO`.

## Place

```python
# Limit (rests or crosses)
order = client.place_limit_order(
    market="btc-updown-5m", side="BUY", outcome="YES",
    price="0.62", size=1000,
    post_only=True,                 # reject if it would cross
    client_order_id="abc-123",      # idempotency key
)

# Market (defaults to IOC)
order = client.place_market_order(market="m1", side="BUY", outcome="YES", size=250)

# Generic
order = client.place_order(
    market="m1", side="BUY_YES", order_type="LIMIT",
    time_in_force="GTC", price="0.62", size=1000,
)
```

The returned `Order`:

```python
order.order_id
order.status          # OPEN | PARTIALLY_FILLED | FILLED | CANCELED | REJECTED
order.side            # "BUY_YES"
order.outcome         # "YES"
order.action          # "BUY"
order.price           # Decimal
order.size, order.filled_size, order.remaining_size
order.client_order_id
order.fills           # list[Fill] generated at submission
order.is_open, order.is_terminal
```

## Dry-run the buying-power check

```python
decision = client.validate_order(market="m1", side="BUY_YES", price="0.62", size=1000)
print(decision["valid"], decision["required_collateral"], decision["available_after_trade"])
```

## Cancel

```python
client.cancel_order("ord-m1-7")                  # market inferred from the id
client.cancel_order("ord-m1-7", market="m1")     # or pass it explicitly
client.cancel_order_by_client_id("abc-123")      # by your idempotency key
client.cancel_all_orders()                       # all open orders
client.cancel_all_orders(market="m1")            # scoped to one market
```

## Modify (cancel / replace)

UMBRA has no in-place amend. `modify_order` cancels the order and submits a replacement
carrying the original parameters with your overrides applied; it returns the new order.

```python
new_order = client.modify_order("ord-m1-7", price="0.63", size=800)
```

## Read

```python
client.get_order("ord-m1-7")
client.get_orders(limit=250)        # all (auto-paginates across cursor pages)
client.get_open_orders()            # resting only
client.get_order_history()          # closed (filled/canceled/rejected)
client.get_orders(market="m1", open_only=True)
```

Pass `limit=None` to fetch every page.

## Rejections

A rejected order raises a typed exception (a subclass of `OrderRejectedError`):

```python
from umbra import InsufficientFundsError, MarketClosedError, OrderRejectedError

try:
    client.place_limit_order(market="m1", side="BUY_YES", price="0.62", size=1_000_000)
except InsufficientFundsError as e:
    print("buying-power gate:", e.validation)
except MarketClosedError:
    print("market not open")
except OrderRejectedError as e:
    print("rejected:", e.reason)   # e.g. POST_ONLY_WOULD_CROSS, FOK_UNFILLABLE
```

## Idempotency & safe retries

A `POST` that carries a `client_order_id` is treated as idempotent, so the SDK will safely
retry it on transient failures. Always pass one for order submission in production.
