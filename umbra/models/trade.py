"""Trade models — public anonymized prints and the user's own fills."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..utils.money import to_decimal

__all__ = ["Trade", "Fill"]


@dataclass(frozen=True)
class Trade:
    """An anonymized public-tape print.

    Carries no counterparty identity (dark-pool anonymity). ``taker_book_side`` tells you
    whether the aggressor was buying (``BID``) or selling (``ASK``) YES; :attr:`aggressor_side`
    renders that as ``BUY``/``SELL``.
    """

    trade_id: str
    market_id: str
    price: Decimal
    quantity: int
    taker_book_side: str  # "BID" | "ASK"
    seq: int
    ts: int | None = None
    raw: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def aggressor_side(self) -> str:
        """``BUY`` if the aggressor lifted the offer, ``SELL`` if it hit the bid."""
        return "BUY" if self.taker_book_side == "BID" else "SELL"

    @classmethod
    def from_api(cls, data: dict) -> Trade:
        return cls(
            trade_id=data["trade_id"],
            market_id=data.get("market_id", ""),
            price=to_decimal(data.get("price")),
            quantity=int(data.get("quantity") or 0),
            taker_book_side=data.get("taker_book_side", ""),
            seq=int(data.get("seq") or 0),
            ts=data.get("ts"),
            raw=data,
        )


@dataclass(frozen=True)
class Fill:
    """One of the authenticated user's own executions, from their perspective.

    ``role`` is ``taker`` (paid the fee) or ``maker`` (received the rebate); ``side`` is the
    user's YES book side (``BUY_YES``/``SELL_YES``); ``fee_or_rebate`` is the signed amount
    relevant to ``role``. Carries no counterparty identity.
    """

    trade_id: str
    market_id: str
    price: Decimal
    quantity: int
    side: str
    role: str  # "taker" | "maker"
    fee_or_rebate: Decimal
    settlement_status: str = "PENDING"
    order_id: str | None = None
    seq: int | None = None
    ts: int | None = None
    raw: dict = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_api(cls, data: dict) -> Fill:
        """Parse a ``UserFillRecord`` (GET /user/fills) into a :class:`Fill`."""
        return cls(
            trade_id=data["trade_id"],
            market_id=data.get("market_id", ""),
            price=to_decimal(data.get("price")),
            quantity=int(data.get("quantity") or 0),
            side=data.get("side", ""),
            role=data.get("role", ""),
            fee_or_rebate=to_decimal(data.get("fee_or_rebate")),
            settlement_status=data.get("settlement_status", "PENDING"),
            order_id=data.get("order_id"),
            seq=data.get("seq"),
            ts=data.get("ts"),
            raw=data,
        )

    @classmethod
    def from_execution(cls, data: dict, *, market_id: str, side: str) -> Fill:
        """Parse an execution leg embedded in a place-order response (``FillResponse``).

        These legs are reported from the taker's perspective; ``net_fee`` is the realized
        fee (positive) or rebate (negative) for the taker.
        """
        return cls(
            trade_id=data["trade_id"],
            market_id=market_id,
            price=to_decimal(data.get("price")),
            quantity=int(data.get("quantity") or 0),
            side=side,
            role="taker",
            fee_or_rebate=to_decimal(data.get("net_fee")),
            settlement_status=data.get("settlement_status", "PENDING"),
            seq=data.get("seq"),
            ts=data.get("ts"),
            raw=data,
        )
