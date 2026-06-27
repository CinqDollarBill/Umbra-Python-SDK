"""Position model — a signed net position in one market with marked PnL."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from ..utils.money import to_decimal, to_optional_decimal

__all__ = ["Position"]


@dataclass(frozen=True)
class Position:
    """A net position in one binary market.

    ``net_qty`` is signed: positive = long YES, negative = long NO (short YES).
    :attr:`quantity` is the absolute size and :attr:`outcome` the side you are long.
    All money fields are :class:`Decimal`.
    """

    market_id: str
    net_qty: int
    avg_entry_price: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Optional[Decimal] = None
    mark_price: Optional[Decimal] = None
    fees_paid: Decimal = Decimal("0")
    rebates_received: Decimal = Decimal("0")
    raw: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def quantity(self) -> int:
        """Absolute position size in contracts."""
        return abs(self.net_qty)

    @property
    def outcome(self) -> Optional[str]:
        """``YES`` if long YES, ``NO`` if long NO, ``None`` if flat."""
        if self.net_qty > 0:
            return "YES"
        if self.net_qty < 0:
            return "NO"
        return None

    @property
    def average_price(self) -> Decimal:
        """Alias for :attr:`avg_entry_price`."""
        return self.avg_entry_price

    @property
    def market_value(self) -> Optional[Decimal]:
        """Current mark-to-market value (``mark_price * net_qty``), or ``None`` without a mark."""
        if self.mark_price is None:
            return None
        return self.mark_price * Decimal(self.net_qty)

    @classmethod
    def from_api(cls, data: dict) -> "Position":
        return cls(
            market_id=data["market_id"],
            net_qty=int(data.get("net_qty") or 0),
            avg_entry_price=to_decimal(data.get("avg_entry_price")),
            realized_pnl=to_decimal(data.get("realized_pnl")),
            unrealized_pnl=to_optional_decimal(data.get("unrealized_pnl")),
            mark_price=to_optional_decimal(data.get("mark_price")),
            fees_paid=to_decimal(data.get("fees_paid")),
            rebates_received=to_decimal(data.get("rebates_received")),
            raw=data,
        )
