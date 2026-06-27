"""Authentication for the UMBRA SDK — Sign-In with Ethereum (SIWE).

The :class:`Authenticator` hides the whole login dance behind a single
``await authenticator.token()``:

1. request a one-time challenge — ``POST /auth/nonce`` returns the exact SIWE message to sign;
2. sign it with ``personal_sign`` (EIP-191);
3. submit the signature — ``POST /auth/verify`` returns a bearer JWT session;
4. cache the JWT and reuse it, transparently re-authenticating shortly before it expires.

Three credential styles are supported, in priority order:

* **private key** — local SIWE signing via the optional ``eth-account`` dependency
  (``pip install "umbra-sdk[wallet]"``). Best for headless bots / market makers.
* **custom signer** — supply ``signer=lambda message: "0x..."`` to sign however you like
  (hardware wallet, remote KMS, MetaMask bridge). Pair it with ``wallet_address=...``.
* **pre-minted token** — supply ``token=...`` if you obtained a JWT out of band; the SDK
  uses it directly and never runs SIWE.

Designed so future credential types (API keys, signed-request auth) slot in without
changing any resource or client code.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from .exceptions import AuthenticationError, ConfigurationError
from .models.wallet import Session

if TYPE_CHECKING:  # pragma: no cover
    from ._http import AsyncHTTP

__all__ = ["Authenticator", "Signer"]

# A signer turns the SIWE message text into a 0x-hex personal_sign signature.
Signer = Callable[[str], str]

# Re-authenticate this many seconds before the JWT's stated expiry.
_REFRESH_LEEWAY = 60


class Authenticator:
    """Resolves and refreshes the bearer token used for authenticated requests."""

    def __init__(
        self,
        http: AsyncHTTP,
        *,
        wallet_address: str | None = None,
        private_key: str | None = None,
        signer: Signer | None = None,
        token: str | None = None,
        user_id: str | None = None,
    ) -> None:
        self._http = http
        self._private_key = private_key
        self._signer = signer
        self._explicit_user_id = user_id
        self._lock = asyncio.Lock()
        self._session: Session | None = None

        # Resolve the wallet address now (deriving it from the private key if needed) so
        # the user_id / private-feed key is available even before the first login.
        self._wallet_address = wallet_address.lower() if wallet_address else None
        if private_key is not None:
            derived = self._derive_address(private_key)
            if self._wallet_address and self._wallet_address != derived:
                raise ConfigurationError(
                    "wallet_address does not match the address derived from private_key"
                )
            self._wallet_address = derived

        # A pre-minted token short-circuits SIWE entirely.
        if token is not None:
            claims = _decode_jwt_claims(token)
            self._session = Session(
                token=token,
                user_id=user_id or str(claims.get("sub") or self._wallet_address or ""),
                wallet_address=self._wallet_address or str(claims.get("addr") or ""),
                expires_at=int(claims.get("exp") or 0),
            )
            if not self._wallet_address:
                self._wallet_address = self._session.wallet_address or None

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #
    @property
    def can_authenticate(self) -> bool:
        """True if this authenticator has any usable credential."""
        return bool(self._session or self._private_key or self._signer)

    @property
    def wallet_address(self) -> str | None:
        return self._wallet_address

    @property
    def user_id(self) -> str | None:
        """The account id, if known (from an active session, explicit value, or address)."""
        if self._explicit_user_id:
            return self._explicit_user_id
        if self._session:
            return self._session.user_id
        return self._wallet_address

    @property
    def session(self) -> Session | None:
        """The current cached session, if logged in."""
        return self._session

    async def token(self) -> str:
        """Return a valid bearer token, authenticating or refreshing as needed."""
        if self._session and not self._is_expiring(self._session):
            return self._session.token
        async with self._lock:
            # Re-check inside the lock — another coroutine may have just logged in.
            if self._session and not self._is_expiring(self._session):
                return self._session.token
            if self._session and not (self._private_key or self._signer):
                # A pre-minted token we cannot refresh: use it until the server rejects it.
                return self._session.token
            self._session = await self._login()
            return self._session.token

    async def authenticate(self) -> Session:
        """Force a fresh SIWE login and return the new :class:`Session`."""
        async with self._lock:
            self._session = await self._login()
            return self._session

    async def require_user_id(self) -> str:
        """Ensure we are logged in and return the authenticated account id."""
        await self.token()
        uid = self.user_id
        if not uid:
            raise ConfigurationError("could not determine the authenticated user_id")
        return uid

    def invalidate(self) -> None:
        """Drop the cached session so the next call re-authenticates."""
        # Keep a non-refreshable pre-minted token; there is nothing to fall back to.
        if self._private_key or self._signer:
            self._session = None

    # ------------------------------------------------------------------ #
    # SIWE flow                                                          #
    # ------------------------------------------------------------------ #
    async def _login(self) -> Session:
        if not self._wallet_address:
            raise ConfigurationError(
                "a wallet_address is required to authenticate (or pass private_key/token)"
            )
        if not (self._private_key or self._signer):
            raise AuthenticationError(
                "no signing credential available; pass private_key=, signer=, or a token="
            )
        challenge = await self._http.request(
            "POST", "/auth/nonce", json={"address": self._wallet_address}, auth=False
        )
        message = challenge["message"]
        signature = self._sign(message)
        verified = await self._http.request(
            "POST",
            "/auth/verify",
            json={"message": message, "signature": signature},
            auth=False,
        )
        return Session.from_api(verified)

    def _sign(self, message: str) -> str:
        if self._signer is not None:
            sig = self._signer(message)
            return sig if sig.startswith("0x") else "0x" + sig
        return self._sign_with_private_key(message)

    def _sign_with_private_key(self, message: str) -> str:
        Account, encode_defunct = _import_eth_account()
        signed = Account.sign_message(encode_defunct(text=message), private_key=self._private_key)
        sig = signed.signature.hex()
        return sig if sig.startswith("0x") else "0x" + sig

    @staticmethod
    def _derive_address(private_key: str) -> str:
        Account, _ = _import_eth_account()
        return Account.from_key(private_key).address.lower()

    @staticmethod
    def _is_expiring(session: Session) -> bool:
        if not session.expires_at:
            return False
        return time.time() >= (session.expires_at - _REFRESH_LEEWAY)


# --------------------------------------------------------------------------- #
# Helpers.                                                                     #
# --------------------------------------------------------------------------- #
def _import_eth_account():
    """Import ``eth-account`` lazily with a friendly error if it is missing."""
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ConfigurationError(
            "local SIWE signing requires the 'eth-account' package. Install it with "
            '`pip install "umbra-sdk[wallet]"`, or pass a custom signer=... / a '
            "pre-minted token=..."
        ) from exc
    return Account, encode_defunct


def _decode_jwt_claims(token: str) -> dict:
    """Best-effort decode of a JWT payload (no signature check — we read our own session)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)  # restore base64 padding
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError, binascii.Error, json.JSONDecodeError):
        return {}
