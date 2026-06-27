"""Decimal-safe money/price parsing.

The exchange serializes all money and prices as JSON **strings** (e.g. ``"0.6"``,
``"999757.6000"``) precisely so clients never coerce them through binary floats. The SDK
honors that: every monetary field on a model is a :class:`decimal.Decimal`, parsed here.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

__all__ = ["to_decimal", "to_optional_decimal"]

Number = str | int | float | Decimal | None


def to_decimal(value: Number, default: Decimal = Decimal("0")) -> Decimal:
    """Parse a money/price value into a :class:`Decimal`, falling back to ``default``.

    ``float`` inputs are routed through ``str`` first to avoid binary-float artifacts.
    """
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        value = repr(value)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def to_optional_decimal(value: Number) -> Decimal | None:
    """Parse a money/price value into a :class:`Decimal`, or ``None`` if absent.

    Distinguishes "no quote" (``None``) from a real zero — used for nullable price fields
    like ``best_bid`` / ``last_trade_price``.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        value = repr(value)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
