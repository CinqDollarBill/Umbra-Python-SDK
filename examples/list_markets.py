"""List markets and the discovery helpers (no authentication required).

    python examples/list_markets.py
"""

import os

from umbra import Client

client = Client(api_url=os.environ.get("UMBRA_API_URL", "http://localhost:8000"))

print("Categories:", client.get_categories())

print("\nAll markets:")
for m in client.get_markets(limit=10):
    print(f"  {m.slug:<28} {m.status:<8} {m.category or '-':<10} {m.title}")

print("\nCrypto markets:")
for m in client.get_crypto_markets(limit=5):
    print(f"  {m.slug} — {m.title}")

print("\nSearch 'btc':")
for m in client.search_markets("btc", limit=5):
    print(f"  {m.slug} — {m.title}")

client.close()
