"""Enumerations for the UMBRA SDK — order sides, types, lifecycles, categories.

All members are ``str``-valued and equal their wire spelling, so they serialize directly
and compare equal to the raw strings the API returns.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "Side",
    "Outcome",
    "OrderType",
    "TimeInForce",
    "OrderStatus",
    "MarketStatus",
    "Category",
    "resolve_side",
]


class Side(str, Enum):
    """The four explicit order sides the matching engine accepts.

    A binary market has a single internal YES book; the four sides normalize onto it::

        BUY_YES  -> bid YES
        SELL_YES -> ask YES
        BUY_NO   -> ask YES  (buying NO == selling YES)
        SELL_NO  -> bid YES  (selling NO == buying YES)

    Prefer :func:`resolve_side` to build a side from a friendly ``("BUY"/"SELL", "YES"/"NO")``
    pair.
    """

    BUY_YES = "BUY_YES"
    SELL_YES = "SELL_YES"
    BUY_NO = "BUY_NO"
    SELL_NO = "SELL_NO"


class Outcome(str, Enum):
    """A binary market outcome / token."""

    YES = "YES"
    NO = "NO"


class OrderType(str, Enum):
    """Order pricing semantics."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"


class TimeInForce(str, Enum):
    """Order lifetime semantics.

    ``GTC`` rests until canceled, ``IOC`` fills what it can immediately then cancels the
    rest, ``FOK`` requires the whole order to fill immediately or is killed.
    """

    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class OrderStatus(str, Enum):
    """Lifecycle status of an order."""

    NEW = "NEW"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


class MarketStatus(str, Enum):
    """Lifecycle status of a market (only ``OPEN`` admits new orders)."""

    UPCOMING = "UPCOMING"
    OPEN = "OPEN"
    HALTED = "HALTED"
    SETTLED = "SETTLED"
    ARCHIVED = "ARCHIVED"
    INVALIDATED = "INVALIDATED"


class Category(str, Enum):
    """Well-known market categories used by the discovery helpers."""

    CRYPTO = "crypto"
    POLITICS = "politics"
    SPORTS = "sports"


# Accepted spellings for the friendly action / outcome inputs.
_BUY = {"BUY", "B", "BID", "LONG"}
_SELL = {"SELL", "S", "ASK", "SHORT"}
_YES = {"YES", "Y", "1", "TRUE"}
_NO = {"NO", "N", "0", "FALSE"}

_SIDE_TABLE = {
    ("BUY", "YES"): Side.BUY_YES,
    ("SELL", "YES"): Side.SELL_YES,
    ("BUY", "NO"): Side.BUY_NO,
    ("SELL", "NO"): Side.SELL_NO,
}


def resolve_side(
    side: str | Side,
    outcome: str | Outcome | None = None,
) -> Side:
    """Resolve a friendly ``(side, outcome)`` into one of the four explicit :class:`Side` values.

    Accepts, in order of preference:

    * an explicit side already (``"BUY_YES"`` / :class:`Side`) — returned as-is;
    * an action + outcome pair, e.g. ``resolve_side("buy", "yes")`` or
      ``resolve_side("sell", Outcome.NO)``.

    Raises :class:`ValueError` for an unrecognized combination.
    """
    if isinstance(side, Side):
        return side
    raw = str(side).strip().upper().replace("-", "_").replace(" ", "_")

    # Already an explicit four-way side?
    if raw in Side.__members__:
        return Side[raw]

    # Action + outcome pair.
    action = "BUY" if raw in _BUY else "SELL" if raw in _SELL else None
    if action is None:
        raise ValueError(
            f"unrecognized side {side!r}; use BUY/SELL with an outcome, or an explicit "
            f"BUY_YES/SELL_YES/BUY_NO/SELL_NO"
        )

    out_raw = str(outcome).strip().upper() if outcome is not None else "YES"
    outcome_norm = "YES" if out_raw in _YES else "NO" if out_raw in _NO else None
    if outcome_norm is None:
        raise ValueError(f"unrecognized outcome {outcome!r}; use 'YES' or 'NO'")

    return _SIDE_TABLE[(action, outcome_norm)]
