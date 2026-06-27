# Authentication

UMBRA authenticates with **Sign-In with Ethereum (SIWE)**. Your wallet is your account.
The SDK runs the entire flow for you:

1. `POST /auth/nonce` — request a one-time challenge (the exact message to sign);
2. sign it with `personal_sign` (EIP-191);
3. `POST /auth/verify` — exchange the signature for a bearer **JWT** session;
4. cache the JWT and **refresh** it shortly before it expires.

This happens lazily on the first authenticated call. Public calls (markets, NBBO, trade
tape) need no credentials.

## Credential styles

### 1. Private key (local signing)

Best for headless bots and market makers. Requires the `wallet` extra
(`pip install "umbra-sdk[wallet]"`).

```python
from umbra import Client

client = Client(api_url="https://api.umbra.exchange", private_key="0x...")
```

The wallet address is derived from the key. Load the key from the environment or a secrets
manager — never hardcode it.

### 2. Custom signer

Sign however you like — a hardware wallet, a remote KMS, or a browser/MetaMask bridge.
Provide the signer plus the wallet address.

```python
def my_signer(message: str) -> str:
    # return a 0x-hex EIP-191 personal_sign signature of `message`
    ...

client = Client(
    api_url="https://api.umbra.exchange",
    wallet_address="0xYourAddress",
    signer=my_signer,
)
```

### 3. Pre-minted token

If you already hold a JWT (obtained out of band), use it directly — no SIWE is performed.

```python
client = Client(api_url="https://api.umbra.exchange", token="eyJ...")
```

## Inspecting the session

Authentication is lazy, but you can force it and inspect the result:

```python
session = client.authenticate()
print(session.user_id, session.wallet_address, session.expires_at)

print(client.user_id)        # the authenticated account id
print(client.session)        # the cached Session, or None

print(client.me())           # GET /auth/me — account + login history
```

## Token lifecycle

- The token is cached and reused across calls.
- It is refreshed automatically ~60s before its stated expiry (when signing credentials are
  available).
- On an unexpected `401`, the SDK re-authenticates once and retries the request.

> A pre-minted token cannot be refreshed; once it expires you must supply a new one.
