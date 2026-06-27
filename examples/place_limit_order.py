"""Place a limit order (BUY YES) and print the result.

export UMBRA_API_URL="http://localhost:8000"
export UMBRA_PRIVATE_KEY="0x..."
python examples/place_limit_order.py <market-slug-or-id>
"""

import os
import sys
import uuid

from umbra import Client, OrderRejectedError

market = sys.argv[1] if len(sys.argv) > 1 else "btc-updown-5m"
client = Client(
    api_url=os.environ.get("UMBRA_API_URL", "http://localhost:8000"),
    private_key=os.environ["UMBRA_PRIVATE_KEY"],
)

try:
    order = client.place_limit_order(
        market=market,
        side="BUY",
        outcome="YES",
        price="0.62",
        size=1000,
        post_only=False,
        client_order_id=f"demo-{uuid.uuid4().hex[:8]}",  # idempotency key
    )
    print(f"Order {order.order_id}: {order.status}")
    print(f"  filled {order.filled_size} / {order.size}  (remaining {order.remaining_size})")
    for fill in order.fills:
        print(f"  fill {fill.trade_id}: {fill.quantity} @ {fill.price}  fee {fill.fee_or_rebate}")
except OrderRejectedError as exc:
    print(f"Rejected ({exc.reason}): {exc.message}")

client.close()
