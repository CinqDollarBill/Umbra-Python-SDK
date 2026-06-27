"""Cancel a single order, or cancel everything resting.

    export UMBRA_PRIVATE_KEY="0x..."
    python examples/cancel_order.py <order-id>      # cancel one
    python examples/cancel_order.py --all           # cancel all open orders
"""

import os
import sys

from umbra import Client, OrderRejectedError

client = Client(
    api_url=os.environ.get("UMBRA_API_URL", "http://localhost:8000"),
    private_key=os.environ["UMBRA_PRIVATE_KEY"],
)

arg = sys.argv[1] if len(sys.argv) > 1 else "--all"

if arg == "--all":
    canceled = client.cancel_all_orders()
    print(f"Canceled {len(canceled)} order(s): {[o.order_id for o in canceled]}")
else:
    try:
        # market is inferred from the order id (ord-{market}-{seq}).
        order = client.cancel_order(arg)
        print(f"{order.order_id}: {order.status}")
    except OrderRejectedError as exc:
        print(f"Could not cancel ({exc.reason}): {exc.message}")

client.close()
