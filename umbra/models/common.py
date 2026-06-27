"""Shared response models: NBBO, order book (NBBO-only), account balance, page envelope."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Generic, TypeVar

from ..utils.money import to_decimal, to_optional_decimal

__all__ = ["Nbbo", "BookLevel", "OrderBook", "Account", "Page"]


@dataclass(frozen=True)
class Nbbo:
    """Top-of-book market data — the only quote surface a dark pool exposes.

    Best bid/ask and the aggregate size resting at *exactly* that best level, plus the
    last trade price. There is deliberately no depth/ladder: resting orders and book depth
    are never published.
    """

    market_id: str
    best_bid: Decimal | None
    best_bid_size: int
    best_ask: Decimal | None
    best_ask_size: int
    last_trade_price: Decimal | None
    raw: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def mid(self) -> Decimal | None:
        """Midpoint of best bid/ask, or ``None`` if either side is empty."""
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2

    @property
    def spread(self) -> Decimal | None:
        """Best ask minus best bid, or ``None`` if either side is empty."""
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    @classmethod
    def from_api(cls, data: dict) -> Nbbo:
        return cls(
            market_id=data["market_id"],
            best_bid=to_optional_decimal(data.get("best_bid")),
            best_bid_size=int(data.get("best_bid_size") or 0),
            best_ask=to_optional_decimal(data.get("best_ask")),
            best_ask_size=int(data.get("best_ask_size") or 0),
            last_trade_price=to_optional_decimal(data.get("last_trade_price")),
            raw=data,
        )


@dataclass(frozen=True)
class BookLevel:
    """A single price level (price + aggregate size)."""

    price: Decimal
    size: int


@dataclass(frozen=True)
class OrderBook:
    """A book-shaped view of a market, collapsed to NBBO (at most one level per side).

    UMBRA is a dark pool: this is **not** a depth book. ``bids`` and ``asks`` each contain
    at most one :class:`BookLevel` — the best bid and best ask. It exists only to give
    book-oriented clients a familiar shape; use :class:`Nbbo` directly if you prefer the
    flat form.
    """

    market_id: str
    bids: list[BookLevel]
    asks: list[BookLevel]
    last_trade_price: Decimal | None = None
    raw: dict = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_nbbo(cls, nbbo: Nbbo) -> OrderBook:
        bids = [BookLevel(nbbo.best_bid, nbbo.best_bid_size)] if nbbo.best_bid is not None else []
        asks = [BookLevel(nbbo.best_ask, nbbo.best_ask_size)] if nbbo.best_ask is not None else []
        return cls(
            market_id=nbbo.market_id,
            bids=bids,
            asks=asks,
            last_trade_price=nbbo.last_trade_price,
            raw=nbbo.raw,
        )


@dataclass(frozen=True)
class Account:
    """A trading-account balance snapshot (the buying power the engine reserves against)."""

    user_id: str
    cash: Decimal
    reserved_margin: Decimal
    available: Decimal
    raw: dict = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_api(cls, data: dict) -> Account:
        return cls(
            user_id=data.get("user_id", ""),
            cash=to_decimal(data.get("cash")),
            reserved_margin=to_decimal(data.get("reserved_margin")),
            available=to_decimal(data.get("available")),
            raw=data,
        )


ItemT = TypeVar("ItemT")


@dataclass
class Page(Generic[ItemT]):
    """A single page of a cursor-paginated list.

    Returned by the ``*_page`` variants. Echo :attr:`next_cursor` back via the ``cursor``
    argument to fetch the following page; an empty cursor marks the last page. Prefer the
    plain list methods (which auto-paginate) unless you need manual cursor control.
    """

    data: list[ItemT]
    next_cursor: str = ""

    @property
    def has_more(self) -> bool:
        """True if another page is available."""
        return bool(self.next_cursor)

    def __iter__(self):  # pragma: no cover - convenience
        return iter(self.data)

    def __len__(self) -> int:  # pragma: no cover - convenience
        return len(self.data)
