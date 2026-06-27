"""Wallet / balances resource (authenticated).

Three balance surfaces:

* :meth:`get_wallet_balance` — the internal *trading* balance the matching engine reserves
  against (cash / reserved margin / available). This is your buying power on the venue.
* :meth:`get_wallet_assets` — the wallet's *live on-chain* ETH + USDC balances.
* :meth:`get_usdc_balance` — just the live on-chain USDC balance (the JIT buying power that
  gates order admission).
"""

from __future__ import annotations

from ._http import AsyncHTTP
from .auth import Authenticator
from .models.common import Account
from .models.wallet import UsdcBalance, WalletAssets

__all__ = ["Balances"]


class Balances:
    """Read trading balance and live on-chain wallet balances."""

    def __init__(self, http: AsyncHTTP, auth: Authenticator) -> None:
        self._http = http
        self._auth = auth

    async def get_wallet_balance(self) -> Account:
        """Return the internal trading balance (cash / reserved margin / available)."""
        data = await self._http.request("GET", "/wallet/balance", auth=True)
        return Account.from_api(data)

    async def get_wallet_assets(self) -> WalletAssets:
        """Return the wallet's live on-chain ETH + USDC balances."""
        data = await self._http.request("GET", "/wallet/assets", auth=True)
        return WalletAssets.from_api(data)

    async def get_usdc_balance(self) -> UsdcBalance:
        """Return the wallet's live on-chain USDC balance (the JIT buying power)."""
        data = await self._http.request("GET", "/wallet/usdc-balance", auth=True)
        return UsdcBalance.from_api(data)
