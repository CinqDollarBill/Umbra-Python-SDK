# Error Handling

Every exception the SDK raises derives from `UmbraError`. Raw `httpx`/transport errors are
never surfaced — they are translated into the typed exceptions below.

```python
from umbra import (
    UmbraError,            # base class — catch-all
    ConfigurationError,    # bad/missing config or credentials (raised locally)
    APIError,              # generic API error (e.g. 5xx after retries)
    AuthenticationError,   # 401 / auth required / SIWE failure
    PermissionError,       # 403
    NotFoundError,         # 404
    ValidationError,       # 422 (request schema)
    RateLimitError,        # 429
    NetworkError,          # connection/timeout after retries
    OrderRejectedError,    # an order was rejected
    MarketClosedError,     #   ↳ market not open
    InsufficientFundsError,#   ↳ buying-power gate failed
    WebSocketError,        # WebSocket-level failure
)
```

## Status mapping

| HTTP / context                | Exception                                  |
|-------------------------------|--------------------------------------------|
| `401`                         | `AuthenticationError`                      |
| `403`                         | `PermissionError`                          |
| `404`                         | `NotFoundError`                            |
| `409` market state            | `MarketClosedError`                        |
| `409` funds                   | `InsufficientFundsError`                   |
| `4xx`/business order reject   | `OrderRejectedError` (or a subclass)       |
| `422`                         | `ValidationError`                          |
| `429`                         | `RateLimitError`                           |
| `5xx` (after retries)         | `APIError`                                 |
| network / timeout             | `NetworkError`                             |

## Inspecting an error

`APIError` (and its subclasses) carry context:

```python
try:
    client.get_market("nope")
except APIError as e:
    e.status_code     # 404
    e.code            # stable machine code, when the server provides one
    e.message         # human-readable
    e.body            # the raw decoded error body
```

`OrderRejectedError` adds the engine `reason` and the buying-power `validation` (when the
rejection came from the funding gate):

```python
try:
    client.place_limit_order(market="m1", side="BUY_YES", price="0.62", size=999999999)
except OrderRejectedError as e:
    print(e.reason)        # e.g. "INSUFFICIENT_FUNDS", "POST_ONLY_WOULD_CROSS"
    print(e.validation)    # {"valid": False, "required_collateral": "...", ...}
```

`ValidationError.errors` holds the structured `detail` list; `RateLimitError.retry_after`
holds the server-suggested cool-off (seconds).

## Retries

Transient failures are retried automatically with exponential backoff + jitter:

- **Retried:** connection errors, timeouts (idempotent calls), `429`, `5xx`.
- **Never retried:** invalid user requests (`4xx` other than `429`).
- A non-idempotent `POST` is only retried when it carries a `client_order_id`.

Tune the policy on the client:

```python
Client(api_url=URL, retries=5, backoff_factor=0.5, backoff_max=10.0, timeout=30.0)
```

## A robust pattern

```python
from umbra import UmbraError, RateLimitError, NetworkError

try:
    order = client.place_limit_order(
        market="m1", side="BUY_YES", price="0.62", size=1000, client_order_id="k1",
    )
except RateLimitError as e:
    ...  # already retried; back off further or shed load
except NetworkError:
    ...  # connectivity problem
except UmbraError as e:
    ...  # everything else
```
