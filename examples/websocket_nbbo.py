"""Stream live NBBO updates over WebSocket (with auto-reconnect + heartbeat).

    python examples/websocket_nbbo.py [market-slug-or-id]

Omit the market argument to stream every market's NBBO.
"""

import os
import sys
import time

from umbra import Client

market = sys.argv[1] if len(sys.argv) > 1 else None
client = Client(api_url=os.environ.get("UMBRA_API_URL", "http://localhost:8000"))

ws = client.websocket()


def on_nbbo(data):
    print(f"NBBO {data['market_id']}: bid {data.get('best_bid')} / ask {data.get('best_ask')}")


ws.on("heartbeat", lambda _: print("· heartbeat"))
ws.subscribe_nbbo(market, handler=on_nbbo)
print("Streaming NBBO — Ctrl-C to stop.")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    ws.close()
    client.close()
