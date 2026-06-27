"""Place a market order (IOC) and print the executions.

export UMBRA_PRIVATE_KEY="0x..."
python examples/place_market_order.py <market-slug-or-id>
"""

import os
import sys

from umbra import Client, OrderRejectedError

market = sys.argv[1] if len(sys.argv) > 1 else "btc-updown-5m"
client = Client(
    api_url=os.environ.get("UMBRA_API_URL", "http://localhost:8000"),
    private_key=os.environ["UMBRA_PRIVATE_KEY"],
)

# Optional dry-run of the buying-power check before sending.
check = client.validate_order(market=market, side="BUY_YES", size=500, order_type="MARKET")
print("validate:", check["valid"], "required_collateral:", check["required_collateral"])

try:
    order = client.place_market_order(market=market, side="BUY", outcome="YES", size=500)
    print(f"Order {order.order_id}: {order.status}, filled {order.filled_size}")
except OrderRejectedError as exc:
    print(f"Rejected ({exc.reason}): {exc.message}")

client.close()
