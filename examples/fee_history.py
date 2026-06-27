"""Print fee/rebate history and the aggregate summary.

    export UMBRA_PRIVATE_KEY="0x..."
    python examples/fee_history.py
"""

import os

from umbra import Client

client = Client(
    api_url=os.environ.get("UMBRA_API_URL", "http://localhost:8000"),
    private_key=os.environ["UMBRA_PRIVATE_KEY"],
)

summary = client.get_fee_summary()
print(f"Fees paid:      {summary.total_fees_paid}")
print(f"Rebates earned: {summary.total_rebates_received}")
print(f"Net fees:       {summary.net_fees}  ({'net earner' if summary.is_net_earner else 'net payer'})")
print(f"Maker/Taker trades: {summary.maker_trades}/{summary.taker_trades}\n")

print("Recent fee entries:")
for e in client.get_fee_history(limit=20):
    print(f"  {e.timestamp or e.ts}  {e.role:<5} {e.side:<4} {e.market_id:<14} net={e.net_fee}")

client.close()
