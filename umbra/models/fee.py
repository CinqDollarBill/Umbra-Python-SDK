"""Fee models — one fee/rebate ledger entry and the aggregate summary."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from ..utils.money import to_decimal

__all__ = ["FeeEntry", "FeeSummary"]


@dataclass(frozen=True)
class FeeEntry:
    """One immutable fee/rebate record for the user's participation in a trade.

    ``net_fee`` is the participant's impact: positive when a ``TAKER`` (fee paid), negative
    when a ``MAKER`` (rebate earned). Money/rates are :class:`Decimal`.
    """

    entry_id: str
    trade_id: str
    market_id: str
    role: str  # "TAKER" | "MAKER"
    side: str  # "BUY" | "SELL" (YES terms)
    fee_rate: Decimal
    rebate_rate: Decimal
    fee_amount: Decimal
    rebate_amount: Decimal
    net_fee: Decimal
    currency: str = "USDC"
    market_slug: Optional[str] = None
    seq: Optional[int] = None
    ts: Optional[int] = None
    timestamp: Optional[str] = None
    raw: dict = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_api(cls, data: dict) -> "FeeEntry":
        return cls(
            entry_id=data.get("entry_id", ""),
            trade_id=data.get("trade_id", ""),
            market_id=data.get("market_id", ""),
            role=data.get("role", ""),
            side=data.get("side", ""),
            fee_rate=to_decimal(data.get("fee_rate")),
            rebate_rate=to_decimal(data.get("rebate_rate")),
            fee_amount=to_decimal(data.get("fee_amount")),
            rebate_amount=to_decimal(data.get("rebate_amount")),
            net_fee=to_decimal(data.get("net_fee")),
            currency=data.get("currency", "USDC"),
            market_slug=data.get("market_slug"),
            seq=data.get("seq"),
            ts=data.get("ts"),
            timestamp=data.get("timestamp"),
            raw=data,
        )


@dataclass(frozen=True)
class FeeSummary:
    """Aggregate fee/rebate statistics for a user.

    ``net_fees`` = ``total_fees_paid`` − ``total_rebates_received``; a negative value means
    the user earned more in rebates than it paid in fees.
    """

    user_id: str
    currency: str
    total_fees_paid: Decimal
    total_rebates_received: Decimal
    net_fees: Decimal
    maker_trades: int
    taker_trades: int
    average_fee_per_trade: Decimal
    average_rebate_per_trade: Decimal
    raw: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def is_net_earner(self) -> bool:
        """True if the user earned more in rebates than it paid in fees."""
        return self.net_fees < 0

    @classmethod
    def from_api(cls, data: dict) -> "FeeSummary":
        return cls(
            user_id=data.get("user_id", ""),
            currency=data.get("currency", "USDC"),
            total_fees_paid=to_decimal(data.get("total_fees_paid")),
            total_rebates_received=to_decimal(data.get("total_rebates_received")),
            net_fees=to_decimal(data.get("net_fees")),
            maker_trades=int(data.get("maker_trades") or 0),
            taker_trades=int(data.get("taker_trades") or 0),
            average_fee_per_trade=to_decimal(data.get("average_fee_per_trade")),
            average_rebate_per_trade=to_decimal(data.get("average_rebate_per_trade")),
            raw=data,
        )
