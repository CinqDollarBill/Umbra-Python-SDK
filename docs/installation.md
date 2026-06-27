# Installation

The SDK supports Python 3.10+.

```bash
pip install umbra-sdk
```

The import name is `umbra`:

```python
import umbra
from umbra import Client, AsyncUmbraClient
```

## Optional: local SIWE signing

To sign the Sign-In-with-Ethereum challenge locally with a private key, install the
`wallet` extra (which adds `eth-account`):

```bash
pip install "umbra-sdk[wallet]"
```

You only need this for the `private_key=` credential style. If you authenticate with a
**custom signer** or a **pre-minted token**, the base install is enough.

## Dependencies

- `httpx` — HTTP transport (async + sync)
- `websockets` — real-time feeds
- `eth-account` *(optional, `[wallet]`)* — local SIWE signing

## Development install

```bash
git clone https://github.com/CinqDollarBill/Umbra-Python-SDK
cd Umbra-Python-SDK
pip install -e ".[dev]"
pytest
```
