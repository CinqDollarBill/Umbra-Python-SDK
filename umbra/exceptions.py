"""Exception hierarchy for the UMBRA SDK.

Every error the SDK raises derives from :class:`UmbraError`, so a caller can catch the
whole family with a single ``except UmbraError``. Raw ``httpx``/transport errors are
never surfaced to SDK users — they are translated into the typed exceptions below by the
HTTP layer (see :mod:`umbra._http`).

Mapping summary (HTTP status / context -> exception):

    401                          -> AuthenticationError
    403                          -> PermissionError
    404                          -> NotFoundError
    409 (market state)           -> MarketClosedError
    409 (funds)                  -> InsufficientFundsError
    409 (other) / 400 / business -> OrderRejectedError (order context) / APIError
    422                          -> ValidationError
    429                          -> RateLimitError
    5xx                          -> APIError (retried first; raised if retries exhausted)
    network / timeout            -> NetworkError
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = [
    "UmbraError",
    "ConfigurationError",
    "APIError",
    "AuthenticationError",
    "PermissionError",
    "NotFoundError",
    "ValidationError",
    "RateLimitError",
    "NetworkError",
    "OrderRejectedError",
    "MarketClosedError",
    "InsufficientFundsError",
    "WebSocketError",
]


class UmbraError(Exception):
    """Base class for every error raised by the UMBRA SDK."""


class ConfigurationError(UmbraError):
    """The client was constructed or used with an invalid configuration.

    Raised before any network call — e.g. a missing API URL, attempting an authenticated
    call without credentials, or requesting SIWE signing without ``eth-account`` installed.
    """


class APIError(UmbraError):
    """An error returned by the UMBRA API.

    Carries the HTTP ``status_code``, a stable machine ``code`` when the server provides
    one, the human-readable ``message``, and the raw decoded ``body`` for inspection.
    Concrete subclasses (:class:`AuthenticationError`, :class:`RateLimitError`, ...) are
    raised for well-known statuses; :class:`APIError` itself is used for anything else
    (notably ``5xx`` after retries are exhausted).
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        body: Any = None,
        request_method: str | None = None,
        request_path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.body = body
        self.request_method = request_method
        self.request_path = request_path

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        bits = []
        if self.status_code is not None:
            bits.append(f"HTTP {self.status_code}")
        if self.code:
            bits.append(self.code)
        prefix = f"[{' '.join(bits)}] " if bits else ""
        where = ""
        if self.request_method and self.request_path:
            where = f" ({self.request_method} {self.request_path})"
        return f"{prefix}{self.message}{where}"


class AuthenticationError(APIError):
    """Authentication failed or is required (HTTP 401, or a local auth/SIWE failure)."""


class PermissionError(
    APIError
):  # noqa: A001 - intentional domain name; shadows builtin only in this module
    """The authenticated principal is not allowed to perform the action (HTTP 403)."""


class NotFoundError(APIError):
    """The requested resource does not exist (HTTP 404)."""


class ValidationError(APIError):
    """The request failed server-side schema validation (HTTP 422).

    ``errors`` holds the structured ``detail`` list FastAPI returns (each item has
    ``loc``/``msg``/``type``) when available.
    """

    def __init__(self, message: str, *, errors: Any = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.errors = errors


class RateLimitError(APIError):
    """The client exceeded a rate limit (HTTP 429).

    ``retry_after`` is the server-suggested cool-off in seconds when provided.
    """

    def __init__(self, message: str, *, retry_after: float | None = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class NetworkError(UmbraError):
    """A transport-level failure (connection error, timeout) after retries were exhausted."""

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.__cause__ = cause


class OrderRejectedError(APIError):
    """An order was rejected by the exchange.

    ``reason`` is the stable engine reason code (e.g. ``POST_ONLY_WOULD_CROSS``,
    ``FOK_UNFILLABLE``, ``BELOW_MIN_QUANTITY``); ``validation`` carries the buying-power
    decision when the rejection came from the pre-trade funding gate.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: str | None = None,
        validation: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.reason = reason
        self.validation = validation


class MarketClosedError(OrderRejectedError):
    """The target market is not open for trading (halted/settled/unknown state)."""


class InsufficientFundsError(OrderRejectedError):
    """The order failed the buying-power check (not enough available balance/collateral)."""


class WebSocketError(UmbraError):
    """A WebSocket-level failure (handshake rejected, auth failed, stream error)."""


# Engine reason codes that mean "market not open for trading".
_MARKET_CLOSED_REASONS = {"MARKET_NOT_OPEN", "UNKNOWN_MARKET", "MARKET_CLOSED", "USER_SUSPENDED"}
# Engine reason codes that mean "not enough buying power".
_INSUFFICIENT_FUNDS_REASONS = {
    "INSUFFICIENT_FUNDS",
    "INSUFFICIENT_BALANCE",
    "INSUFFICIENT_BUYING_POWER",
}


def order_error_for_reason(
    reason: str | None,
    message: str,
    *,
    validation: Any = None,
    status_code: int | None = None,
    body: Any = None,
) -> OrderRejectedError:
    """Pick the most specific order exception for an engine ``reason`` code."""
    norm = (reason or "").upper()
    kwargs: Mapping[str, Any] = dict(
        reason=reason, validation=validation, status_code=status_code, body=body
    )
    if norm in _MARKET_CLOSED_REASONS:
        return MarketClosedError(message, **kwargs)  # type: ignore[arg-type]
    if norm in _INSUFFICIENT_FUNDS_REASONS:
        return InsufficientFundsError(message, **kwargs)  # type: ignore[arg-type]
    return OrderRejectedError(message, **kwargs)  # type: ignore[arg-type]
