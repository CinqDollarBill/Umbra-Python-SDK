"""Fees resource (authenticated) — fee/rebate history and aggregate summary."""

from __future__ import annotations

from typing import List, Optional

from ._http import AsyncHTTP
from .auth import Authenticator
from .markets import Markets
from .models.fee import FeeEntry, FeeSummary
from .utils.pagination import collect_pages

__all__ = ["Fees"]


class Fees:
    """Read the caller's immutable fee/rebate ledger."""

    def __init__(self, http: AsyncHTTP, auth: Authenticator, markets: Markets) -> None:
        self._http = http
        self._auth = auth
        self._markets = markets

    async def get_fee_history(
        self,
        *,
        market: Optional[str] = None,
        role: Optional[str] = None,
        side: Optional[str] = None,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        sort: str = "-ts",
        limit: Optional[int] = 100,
    ) -> List[FeeEntry]:
        """Return the caller's fee/rebate history (filtered, sorted, auto-paginated).

        ``role`` is ``TAKER``/``MAKER``; ``side`` is ``BUY``/``SELL`` (YES terms); ``sort``
        defaults to newest-first (``-ts``). ``start_ts``/``end_ts`` are epoch nanoseconds.
        """
        user_id = await self._auth.require_user_id()
        market_id = await self._markets.resolve_market_id(market) if market else None

        async def fetch(cursor: str, page_size: int):
            data = await self._http.request(
                "GET", "/user/fees",
                params={
                    "user_id": user_id, "market_id": market_id,
                    "role": role.upper() if role else None,
                    "side": side.upper() if side else None,
                    "start_ts": start_ts, "end_ts": end_ts,
                    "sort": sort, "limit": page_size, "cursor": cursor,
                },
                auth=True,
            )
            return [FeeEntry.from_api(e) for e in data.get("fees", [])], data.get("next_cursor", "")

        return await collect_pages(fetch, limit)

    async def get_fee_summary(
        self,
        *,
        market: Optional[str] = None,
        role: Optional[str] = None,
        side: Optional[str] = None,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
    ) -> FeeSummary:
        """Return aggregate fee/rebate totals for the caller (optionally filtered)."""
        user_id = await self._auth.require_user_id()
        market_id = await self._markets.resolve_market_id(market) if market else None
        data = await self._http.request(
            "GET", "/user/fees/summary",
            params={
                "user_id": user_id, "market_id": market_id,
                "role": role.upper() if role else None,
                "side": side.upper() if side else None,
                "start_ts": start_ts, "end_ts": end_ts,
            },
            auth=True,
        )
        return FeeSummary.from_api(data)

    async def get_trade_fees(self, trade_id: str) -> List[FeeEntry]:
        """Return the caller's full fee/rebate breakdown for one trade (2 rows on a self-trade)."""
        user_id = await self._auth.require_user_id()
        data = await self._http.request(
            "GET", f"/user/fees/{trade_id}", params={"user_id": user_id}, auth=True
        )
        return [FeeEntry.from_api(e) for e in data.get("entries", [])]
