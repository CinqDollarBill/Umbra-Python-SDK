"""List open positions and the account balance.

export UMBRA_PRIVATE_KEY="0x..."
python examples/list_positions.py
"""

import os

from umbra import Client

client = Client(
    api_url=os.environ.get("UMBRA_API_URL", "http://localhost:8000"),
    private_key=os.environ["UMBRA_PRIVATE_KEY"],
)

account = client.get_account()
print(f"Cash {account.cash}  reserved {account.reserved_margin}  available {account.available}\n")

positions = client.get_positions()
if not positions:
    print("No open positions.")
for p in positions:
    print(
        f"  {p.market_id:<18} {p.outcome or 'FLAT':<4} qty={p.quantity:<6} "
        f"avg={p.average_price}  mark={p.mark_price}  uPnL={p.unrealized_pnl}  "
        f"value={p.market_value}"
    )

client.close()
