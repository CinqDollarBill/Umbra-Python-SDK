"""Stream the private per-user feed — live order, position, and balance updates.

This is the authenticated feed; it is delivered only to your own account.

    export UMBRA_PRIVATE_KEY="0x..."
    python examples/websocket_orders.py
"""

import os
import time

from umbra import Client

client = Client(
    api_url=os.environ.get("UMBRA_API_URL", "http://localhost:8000"),
    private_key=os.environ["UMBRA_PRIVATE_KEY"],
)

ws = client.websocket()


def on_order(order):
    print(
        f"ORDER {order['order_id']}: {order['status']} "
        f"({order.get('filled_quantity')}/{order.get('quantity')})"
    )


def on_position(position):
    print(
        f"POSITION {position['market_id']}: net_qty={position['net_qty']} "
        f"uPnL={position.get('unrealized_pnl')}"
    )


def on_balance(account):
    print(f"BALANCE available={account['available']} reserved={account['reserved_margin']}")


# All three share one underlying /ws/user connection.
ws.subscribe_orders(on_order)
ws.subscribe_positions(on_position)
ws.subscribe_balance(on_balance)
print("Streaming your private feed — Ctrl-C to stop.")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    ws.close()
    client.close()
