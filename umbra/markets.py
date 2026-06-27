"""Market discovery + market-data resource (public; no authentication required).

Covers listing/searching markets, resolving a market by slug or id, and the NBBO-only
market-data surface. UMBRA is a dark pool: only top-of-book (NBBO) is ever exposed — there
is no hidden order book to read, and the :meth:`orderbook` helper is just an NBBO rendered
in book shape (at most one level per side).

This resource also owns slug/id resolution (with a short cache) used by the order, position
and trade resources, so a caller can pass a human-readable slug anywhere a market is
expected.
"""

from __future__ import annotations

import time
from typing import List, Optional

from ._http import AsyncHTTP
from .exceptions import NotFoundError
from .models.common import Nbbo, OrderBook
from .models.market import Market

__all__ = ["Markets"]

_CACHE_TTL = 5.0  # seconds; slug resolution tolerates a slightly stale market list


class Markets:
    """Read-only market discovery and NBBO market data."""

    def __init__(self, http: AsyncHTTP) -> None:
        self._http = http
        self._cache: List[Market] = []
        self._cache_at: float = 0.0

    # ------------------------------------------------------------------ #
    # Listing / search / discovery                                       #
    # ------------------------------------------------------------------ #
    async def list(
        self,
        *,
        category: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        refresh: bool = False,
    ) -> List[Market]:
        """List markets, optionally filtered by ``category`` and/or ``status``.

        ``refresh=True`` bypasses the short internal cache.
        """
        markets = await self._all(refresh=refresh)
        if category is not None:
            cat = category.lower()
            markets = [m for m in markets if (m.category or "").lower() == cat]
        if status is not None:
            st = status.upper()
            markets = [m for m in markets if (m.status or "").upper() == st]
        if limit is not None:
            markets = markets[:limit]
        return markets

    async def search(self, query: str, *, limit: Optional[int] = None) -> List[Market]:
        """Return markets whose title contains ``query`` (case-insensitive)."""
        q = (query or "").strip().lower()
        markets = await self._all()
        matches = [m for m in markets if q in (m.title or "").lower()] if q else markets
        return matches[:limit] if limit is not None else matches

    async def categories(self) -> List[str]:
        """Return the sorted set of distinct, non-empty market categories."""
        cats = {m.category for m in await self._all() if m.category}
        return sorted(cats)

    async def get(self, ref: str, *, with_nbbo: bool = True) -> Market:
        """Resolve a market by slug or id and return it (enriched with NBBO by default)."""
        market = await self._find(ref)
        if market is None:
            raise NotFoundError(
                f"no market matching {ref!r}", status_code=404, code="market_not_found"
            )
        if with_nbbo:
            try:
                nbbo = await self.nbbo(market.market_id)
                return market.with_nbbo(nbbo)
            except NotFoundError:
                return market
        return market

    # ------------------------------------------------------------------ #
    # Market data (NBBO only)                                            #
    # ------------------------------------------------------------------ #
    async def nbbo(self, ref: str) -> Nbbo:
        """Return the NBBO (top-of-book) for a market by slug or id."""
        market_id = await self.resolve_market_id(ref)
        data = await self._http.request("GET", f"/markets/{market_id}/nbbo")
        return Nbbo.from_api(data)

    async def orderbook(self, ref: str) -> OrderBook:
        """Return the NBBO rendered in book shape (≤1 level per side — dark pool, no depth)."""
        return OrderBook.from_nbbo(await self.nbbo(ref))

    # ------------------------------------------------------------------ #
    # Resolution + cache                                                 #
    # ------------------------------------------------------------------ #
    async def resolve_market_id(self, ref: str) -> str:
        """Resolve a slug or id to an internal ``market_id``.

        Falls back to returning ``ref`` unchanged when nothing matches, so an explicit
        ``market_id`` always works even if it isn't in the cached listing (the downstream
        call will 404 if it is genuinely unknown).
        """
        market = await self._find(ref)
        return market.market_id if market is not None else ref

    async def _find(self, ref: str) -> Optional[Market]:
        wanted = (ref or "").strip().lower()
        if not wanted:
            return None
        for m in await self._all():
            if any(s.lower() == wanted for s in m.slugs):
                return m
        # Cache may be stale (new market); refresh once and retry.
        for m in await self._all(refresh=True):
            if any(s.lower() == wanted for s in m.slugs):
                return m
        return None

    async def _all(self, *, refresh: bool = False) -> List[Market]:
        now = time.monotonic()
        if refresh or not self._cache or (now - self._cache_at) > _CACHE_TTL:
            data = await self._http.request("GET", "/markets")
            self._cache = [Market.from_api(m) for m in (data or [])]
            self._cache_at = now
        return self._cache
