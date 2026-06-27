"""Market models — a binary YES/NO market and its synthetic YES/NO tokens."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from ..types.enums import MarketStatus
from ..utils.money import to_optional_decimal

__all__ = ["Token", "Market"]


def _slugify(title: str) -> str:
    """Deterministic, URL-safe slug derived from a title (lower-case, hyphenated)."""
    return re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")


@dataclass(frozen=True)
class Token:
    """One side (YES or NO) of a binary market."""

    token_id: str
    outcome: str  # "YES" | "NO"
    price: Optional[Decimal] = None


@dataclass(frozen=True)
class Market:
    """A binary (YES/NO) event market.

    Attributes mirror the exchange's market record. ``slug`` is the best available
    human-readable identifier (the external Polymarket slug when present, else a
    deterministic slug derived from the title). ``best_bid`` / ``best_ask`` are populated
    only when the market was fetched together with its NBBO (e.g. via
    :meth:`~umbra.client.AsyncUmbraClient.get_market`); otherwise they are ``None``.
    """

    market_id: str
    title: str
    status: str
    slug: Optional[str] = None
    category: Optional[str] = None
    outcome: Optional[int] = None  # 1=YES, 0=NO once settled; None while open
    group_id: Optional[str] = None
    group_title: Optional[str] = None
    outcome_label: Optional[str] = None
    asset: Optional[str] = None
    polymarket_slug: Optional[str] = None
    kalshi_slug: Optional[str] = None
    reference_price: Optional[Decimal] = None
    settlement_price: Optional[Decimal] = None
    settlement_window_start: Optional[str] = None
    settlement_window_end: Optional[str] = None
    created_ts: Optional[int] = None
    tokens: List[Token] = field(default_factory=list)
    # Top-of-book, present only when fetched alongside the NBBO.
    best_bid: Optional[Decimal] = None
    best_ask: Optional[Decimal] = None
    last_trade_price: Optional[Decimal] = None
    raw: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def is_open(self) -> bool:
        """True while the market accepts new orders."""
        return self.status == MarketStatus.OPEN.value

    @property
    def is_settled(self) -> bool:
        """True once the market has resolved/closed."""
        return self.status in (
            MarketStatus.SETTLED.value,
            MarketStatus.ARCHIVED.value,
            MarketStatus.INVALIDATED.value,
        )

    @property
    def slugs(self) -> List[str]:
        """All identifiers this market can be matched by (id + every known slug)."""
        candidates = [
            self.market_id,
            self.slug,
            self.polymarket_slug,
            self.kalshi_slug,
            _slugify(self.title),
        ]
        seen: List[str] = []
        for c in candidates:
            if c and c not in seen:
                seen.append(c)
        return seen

    @classmethod
    def from_api(cls, data: dict) -> "Market":
        """Parse a core ``MarketResponse`` dict into a :class:`Market`."""
        title = data.get("title", "")
        poly = data.get("polymarket_slug")
        slug = poly or _slugify(title)
        return cls(
            market_id=data["market_id"],
            title=title,
            status=data.get("status", ""),
            slug=slug,
            category=data.get("category"),
            outcome=data.get("outcome"),
            group_id=data.get("group_id"),
            group_title=data.get("group_title"),
            outcome_label=data.get("outcome_label"),
            asset=data.get("asset"),
            polymarket_slug=poly,
            kalshi_slug=data.get("kalshi_slug"),
            reference_price=to_optional_decimal(data.get("reference_price")),
            settlement_price=to_optional_decimal(data.get("settlement_price")),
            settlement_window_start=data.get("settlement_window_start"),
            settlement_window_end=data.get("settlement_window_end"),
            created_ts=data.get("created_ts"),
            tokens=[
                Token(f"{data['market_id']}-YES", "YES"),
                Token(f"{data['market_id']}-NO", "NO"),
            ],
            raw=data,
        )

    def with_nbbo(self, nbbo) -> "Market":
        """Return a copy enriched with top-of-book fields from an :class:`~umbra.models.common.Nbbo`."""
        from dataclasses import replace

        return replace(
            self,
            best_bid=nbbo.best_bid,
            best_ask=nbbo.best_ask,
            last_trade_price=nbbo.last_trade_price,
            tokens=[
                Token(f"{self.market_id}-YES", "YES", nbbo.last_trade_price or nbbo.mid),
                Token(
                    f"{self.market_id}-NO",
                    "NO",
                    (Decimal("1") - (nbbo.last_trade_price or nbbo.mid))
                    if (nbbo.last_trade_price or nbbo.mid) is not None
                    else None,
                ),
            ],
        )
