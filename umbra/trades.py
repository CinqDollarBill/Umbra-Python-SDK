"""Trades resource — the public anonymized tape and the caller's own fills.

The public tape (:meth:`get_trades` / :meth:`get_trade`) is unauthenticated and carries no
counterparty identity — only price, size, aggressor side, and time. The caller's own
executions (:meth:`get_fills`) require authentication and are reported from the user's
perspective (side / taker-or-maker role / fee or rebate).
"""

from __future__ import annotations

from ._http import AsyncHTTP
from .auth import Authenticator
from .exceptions import NotFoundError
from .markets import Markets
from .models.trade import Fill, Trade
from .utils.pagination import collect_pages

__all__ = ["Trades"]

_MAX_TAPE = 1000


class Trades:
    """Public trade tape and authenticated own-fill history."""

    def __init__(self, http: AsyncHTTP, auth: Authenticator, markets: Markets) -> None:
        self._http = http
        self._auth = auth
        self._markets = markets

    async def get_trades(self, market: str, *, limit: int = 50) -> list[Trade]:
        """Return recent public, anonymized prints for a market (newest first)."""
        market_id = await self._markets.resolve_market_id(market)
        capped = max(1, min(limit, _MAX_TAPE))
        data = await self._http.request(
            "GET", f"/markets/{market_id}/trades", params={"limit": capped}
        )
        # The REST tape is oldest -> newest; present newest first.
        trades = [Trade.from_api(t) for t in (data or [])]
        trades.reverse()
        return trades

    async def get_trade(self, trade_id: str, *, market: str) -> Trade:
        """Look up one public print by id within a market's recent tape."""
        for t in await self.get_trades(market, limit=_MAX_TAPE):
            if t.trade_id == trade_id:
                return t
        raise NotFoundError(f"trade {trade_id!r} not found in {market!r}", code="trade_not_found")

    async def get_fills(self, *, market: str | None = None, limit: int | None = 100) -> list[Fill]:
        """Return the caller's own executions (newest first, auto-paginated)."""
        user_id = await self._auth.require_user_id()
        market_id = await self._markets.resolve_market_id(market) if market else None

        async def fetch(cursor: str, page_size: int):
            data = await self._http.request(
                "GET",
                "/user/fills",
                params={
                    "user_id": user_id,
                    "market_id": market_id,
                    "limit": page_size,
                    "cursor": cursor,
                },
                auth=True,
            )
            return [Fill.from_api(f) for f in data.get("fills", [])], data.get("next_cursor", "")

        return await collect_pages(fetch, limit)
