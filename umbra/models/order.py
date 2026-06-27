"""Order model — a working/closed order plus any executions it generated."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from ..types.enums import OrderStatus
from ..utils.money import to_optional_decimal
from .trade import Fill

__all__ = ["Order"]

_TERMINAL = {OrderStatus.FILLED.value, OrderStatus.CANCELED.value, OrderStatus.REJECTED.value}
_OPEN = {OrderStatus.OPEN.value, OrderStatus.PARTIALLY_FILLED.value, OrderStatus.NEW.value}


def _outcome_for_side(side: Optional[str]) -> Optional[str]:
    if not side:
        return None
    return "NO" if side.endswith("_NO") else "YES"


@dataclass(frozen=True)
class Order:
    """An order's current state.

    ``side`` is the explicit four-way side (``BUY_YES``/...); :attr:`outcome` and
    :attr:`action` decompose it. ``price`` is the limit price in the token's own terms
    (``None`` for market orders). Sizes are integer contract counts. ``fills`` lists the
    executions generated at submission time (empty for a resting order or when reading a
    stored order). ``client_order_id`` round-trips your idempotency key when the SDK
    tracked it.
    """

    order_id: str
    market_id: str
    status: str
    side: Optional[str] = None
    order_type: str = "LIMIT"
    time_in_force: str = "GTC"
    price: Optional[Decimal] = None
    size: int = 0
    filled_size: int = 0
    remaining_size: int = 0
    reason: Optional[str] = None
    post_only: bool = False
    client_order_id: Optional[str] = None
    fills: List[Fill] = field(default_factory=list)
    created_ts: Optional[int] = None
    raw: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def outcome(self) -> Optional[str]:
        """``YES`` or ``NO`` token the order trades, derived from :attr:`side`."""
        return _outcome_for_side(self.side)

    @property
    def action(self) -> Optional[str]:
        """``BUY`` or ``SELL``, derived from :attr:`side`."""
        if not self.side:
            return None
        return "BUY" if self.side.startswith("BUY") else "SELL"

    @property
    def is_open(self) -> bool:
        """True while the order can still rest/fill."""
        return self.status in _OPEN

    @property
    def is_terminal(self) -> bool:
        """True once the order can no longer change (filled/canceled/rejected)."""
        return self.status in _TERMINAL

    @classmethod
    def from_api(cls, data: dict, *, client_order_id: Optional[str] = None) -> "Order":
        """Parse a stored ``OrderRecord`` (GET /user/orders) into an :class:`Order`."""
        qty = int(data.get("quantity") or 0)
        filled = int(data.get("filled_quantity") or 0)
        remaining = data.get("remaining_quantity")
        return cls(
            order_id=data["order_id"],
            market_id=data.get("market_id", ""),
            status=data.get("status", ""),
            side=data.get("side"),
            order_type=data.get("order_type") or "LIMIT",
            time_in_force=data.get("tif") or "GTC",
            price=to_optional_decimal(data.get("limit_price")),
            size=qty,
            filled_size=filled,
            remaining_size=int(remaining if remaining is not None else max(0, qty - filled)),
            reason=data.get("reason"),
            client_order_id=client_order_id,
            created_ts=data.get("ts"),
            raw=data,
        )

    @classmethod
    def from_submit(
        cls,
        result: dict,
        *,
        side: str,
        order_type: str,
        time_in_force: str,
        price: Optional[Decimal],
        size: int,
        post_only: bool = False,
        client_order_id: Optional[str] = None,
    ) -> "Order":
        """Build an :class:`Order` from a place-order engine result + the submitted params.

        The submit result carries the order id, status, reason and the executed legs, but
        not the original side/price/size (those came from the request) — so we thread them
        through here.
        """
        fills_raw = result.get("fills") or []
        market_id = result.get("market_id", "")
        fills = [Fill.from_execution(f, market_id=market_id, side=side) for f in fills_raw]
        filled = sum(f.quantity for f in fills)
        return cls(
            order_id=result.get("order_id", ""),
            market_id=market_id,
            status=result.get("status", "OPEN"),
            side=side,
            order_type=order_type,
            time_in_force=time_in_force,
            price=price,
            size=size,
            filled_size=filled,
            remaining_size=max(0, size - filled),
            reason=result.get("reason"),
            post_only=post_only,
            client_order_id=client_order_id,
            fills=fills,
            raw=result,
        )
