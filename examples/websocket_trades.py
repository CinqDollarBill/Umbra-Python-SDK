"""Stream the live anonymized trade tape over WebSocket.

    python examples/websocket_trades.py [market-slug-or-id]

The tape sends no backlog on connect — backfill with client.get_trades(...) first.
"""

import os
import sys
import time

from umbra import Client

market = sys.argv[1] if len(sys.argv) > 1 else None
client = Client(api_url=os.environ.get("UMBRA_API_URL", "http://localhost:8000"))

# Backfill recent prints before subscribing (only meaningful for a single market).
if market:
    for t in reversed(client.get_trades(market, limit=10)):
        print(f"(backfill) {t.trade_id}: {t.quantity} @ {t.price} [{t.aggressor_side}]")

ws = client.websocket()


def on_trade(data):
    side = "BUY" if data.get("taker_book_side") == "BID" else "SELL"
    print(f"TRADE {data['market_id']}: {data['quantity']} @ {data['price']} [{side}]")


ws.subscribe_trades(market, handler=on_trade)
print("Streaming trade tape — Ctrl-C to stop.")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    ws.close()
    client.close()
