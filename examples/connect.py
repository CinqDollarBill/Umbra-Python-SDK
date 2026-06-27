"""Connect to UMBRA and confirm authentication.

export UMBRA_API_URL="http://localhost:8000"
export UMBRA_PRIVATE_KEY="0x..."        # the wallet that signs the SIWE login
python examples/connect.py
"""

import os

from umbra import Client

client = Client(
    api_url=os.environ.get("UMBRA_API_URL", "http://localhost:8000"),
    private_key=os.environ["UMBRA_PRIVATE_KEY"],
)

# The first authenticated call signs in via SIWE automatically; do it eagerly here.
session = client.authenticate()
print(f"Authenticated as {session.user_id}")
print(f"Wallet: {session.wallet_address}")
print(f"Token expires at (epoch): {session.expires_at}")

client.close()
