"""Positions resource (authenticated)."""

from __future__ import annotations

from typing import List, Optional

from ._http import AsyncHTTP
from .auth import Authenticator
from .markets import Markets
from .models.common import Account
from .models.position import Position

__all__ = ["Positions"]


class Positions:
    """Read the caller's open positions and account balance."""

    def __init__(self, http: AsyncHTTP, auth: Authenticator, markets: Markets) -> None:
        self._http = http
        self._auth = auth
        self._markets = markets

    async def get_positions(self) -> List[Position]:
        """Return all of the caller's open positions (with marked unrealized PnL)."""
        snapshot = await self._snapshot()
        return [Position.from_api(p) for p in snapshot.get("positions", [])]

    async def get_position(self, market: str) -> Optional[Position]:
        """Return the caller's position in one market (by slug or id), or ``None`` if flat."""
        market_id = await self._markets.resolve_market_id(market)
        for p in await self.get_positions():
            if p.market_id == market_id:
                return p
        return None

    async def get_account(self) -> Account:
        """Return the caller's cash / reserved-margin / available-balance snapshot."""
        snapshot = await self._snapshot()
        return Account.from_api(snapshot.get("account", {}))

    async def _snapshot(self) -> dict:
        user_id = await self._auth.require_user_id()
        return await self._http.request(
            "GET", "/user/positions", params={"user_id": user_id}, auth=True
        )
