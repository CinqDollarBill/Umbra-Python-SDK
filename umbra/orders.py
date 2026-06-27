"""Order entry + lifecycle resource (authenticated).

Placement goes through UMBRA's wallet-authenticated, just-in-time funding endpoint: the
order is admitted only if the wallet's live USDC balance covers its collateral. Reads,
cancels, and order history use the account's authoritative order store.

CLIENT ORDER IDS
----------------
The exchange's stored order records are keyed by engine order id (``ord-{market}-{seq}``).
To make ``client_order_id`` a first-class idempotency + handle key, the SDK keeps an
in-process index mapping ``client_order_id <-> order_id`` for orders it placed, so you can
cancel by client id and see your id echoed back on the returned :class:`~umbra.models.order.Order`.

MODIFY
------
The venue has no in-place amend; :meth:`modify_order` is an explicit cancel/replace
(documented as such) that returns the newly placed order.
"""

from __future__ import annotations

from decimal import Decimal

from ._http import AsyncHTTP
from .auth import Authenticator
from .exceptions import (
    ConfigurationError,
    NotFoundError,
    OrderRejectedError,
    order_error_for_reason,
)
from .markets import Markets
from .models.order import Order
from .types.enums import OrderType, Outcome, Side, TimeInForce, resolve_side
from .utils.money import to_optional_decimal
from .utils.pagination import collect_pages

__all__ = ["Orders"]

_ORDER_PREFIX = "ord-"
_TERMINAL = {"FILLED", "CANCELED", "REJECTED"}

PriceLike = str | int | float | Decimal | None


def _coerce_enum(enum_cls, value):
    """Accept either an enum member or its (case-insensitive) string spelling."""
    if isinstance(value, enum_cls):
        return value
    return enum_cls(str(value).upper())


def market_id_from_order_id(order_id: str) -> str:
    """Extract ``market_id`` from ``ord-{market_id}-{seq}`` (market may contain hyphens)."""
    if not order_id or not order_id.startswith(_ORDER_PREFIX):
        raise ConfigurationError(f"cannot infer market from order_id {order_id!r}; pass market=...")
    body = order_id[len(_ORDER_PREFIX) :]
    market_id, _, seq = body.rpartition("-")
    if not market_id or not seq:
        raise ConfigurationError(f"cannot infer market from order_id {order_id!r}; pass market=...")
    return market_id


class Orders:
    """Place, cancel, modify, and read orders."""

    def __init__(self, http: AsyncHTTP, auth: Authenticator, markets: Markets) -> None:
        self._http = http
        self._auth = auth
        self._markets = markets
        # (user_id, client_order_id) -> order_id, and the reverse for echo-back.
        self._coid_to_oid: dict[tuple[str, str], str] = {}
        self._oid_to_coid: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Placement                                                          #
    # ------------------------------------------------------------------ #
    async def place_order(
        self,
        *,
        market: str,
        side: str | Side,
        size: int,
        outcome: str | Outcome | None = None,
        price: PriceLike = None,
        order_type: str | OrderType = OrderType.LIMIT,
        time_in_force: str | TimeInForce = TimeInForce.GTC,
        post_only: bool = False,
        client_order_id: str | None = None,
    ) -> Order:
        """Place an order on UMBRA's book.

        Parameters
        ----------
        market:
            Market slug or id.
        side:
            ``"BUY"``/``"SELL"`` (combined with ``outcome``) or an explicit
            ``"BUY_YES"``/``"SELL_YES"``/``"BUY_NO"``/``"SELL_NO"``.
        outcome:
            ``"YES"`` or ``"NO"`` when ``side`` is the plain ``BUY``/``SELL`` form.
        size:
            Quantity in contracts (positive integer).
        price:
            Limit price in ``[0, 1]`` in the token's own terms. Required for ``LIMIT``,
            must be omitted for ``MARKET``.
        order_type, time_in_force, post_only, client_order_id:
            Standard order parameters. ``post_only`` rejects a limit that would cross.
            ``client_order_id`` is an idempotency key, tracked for cancel-by-client-id.

        Raises
        ------
        InsufficientFundsError, MarketClosedError, OrderRejectedError
            If the order is rejected (buying-power gate, market state, or engine reason).
        """
        market_id = await self._markets.resolve_market_id(market)
        resolved_side = resolve_side(side, outcome)
        otype = _coerce_enum(OrderType, order_type)
        tif = _coerce_enum(TimeInForce, time_in_force)
        dprice = to_optional_decimal(price)

        if otype is OrderType.LIMIT and dprice is None:
            raise ConfigurationError("price is required for LIMIT orders")
        if otype is OrderType.MARKET and dprice is not None:
            raise ConfigurationError("price must be omitted for MARKET orders")
        if size <= 0:
            raise ConfigurationError("size must be a positive integer")

        body = {
            "market_id": market_id,
            "side": resolved_side.value,
            "type": otype.value,
            "quantity": int(size),
            "tif": tif.value,
            "post_only": post_only,
            "client_order_id": client_order_id,
            "price": float(dprice) if dprice is not None else None,
        }
        result = await self._http.request(
            "POST",
            "/orders",
            json=_drop_none(body),
            auth=True,
            idempotent=bool(client_order_id),
        )

        if not result.get("accepted", False):
            reason = result.get("reason")
            validation = result.get("validation")
            raise order_error_for_reason(
                reason,
                _reason_message(reason, validation),
                validation=validation,
                body=result,
            )

        engine = result.get("order") or {}
        order = Order.from_submit(
            engine,
            side=resolved_side.value,
            order_type=otype.value,
            time_in_force=tif.value,
            price=dprice,
            size=int(size),
            post_only=post_only,
            client_order_id=client_order_id,
        )
        if client_order_id and order.order_id:
            await self._remember(client_order_id, order.order_id)
        return order

    async def place_limit_order(
        self,
        *,
        market: str,
        side: str | Side,
        size: int,
        price: PriceLike,
        outcome: str | Outcome | None = None,
        time_in_force: str | TimeInForce = TimeInForce.GTC,
        post_only: bool = False,
        client_order_id: str | None = None,
    ) -> Order:
        """Convenience wrapper for a ``LIMIT`` order."""
        return await self.place_order(
            market=market,
            side=side,
            size=size,
            outcome=outcome,
            price=price,
            order_type=OrderType.LIMIT,
            time_in_force=time_in_force,
            post_only=post_only,
            client_order_id=client_order_id,
        )

    async def place_market_order(
        self,
        *,
        market: str,
        side: str | Side,
        size: int,
        outcome: str | Outcome | None = None,
        time_in_force: str | TimeInForce = TimeInForce.IOC,
        client_order_id: str | None = None,
    ) -> Order:
        """Convenience wrapper for a ``MARKET`` order (defaults to IOC)."""
        return await self.place_order(
            market=market,
            side=side,
            size=size,
            outcome=outcome,
            price=None,
            order_type=OrderType.MARKET,
            time_in_force=time_in_force,
            client_order_id=client_order_id,
        )

    async def validate_order(
        self,
        *,
        market: str,
        side: str | Side,
        size: int,
        outcome: str | Outcome | None = None,
        price: PriceLike = None,
        order_type: str | OrderType = OrderType.LIMIT,
        time_in_force: str | TimeInForce = TimeInForce.GTC,
        post_only: bool = False,
    ) -> dict:
        """Dry-run the buying-power check for an order without placing it.

        Returns the decision dict (``valid``, ``reason``, ``wallet_balance``,
        ``required_collateral``, ``available_after_trade``, ``market_id``).
        """
        market_id = await self._markets.resolve_market_id(market)
        resolved_side = resolve_side(side, outcome)
        otype = _coerce_enum(OrderType, order_type)
        tif = _coerce_enum(TimeInForce, time_in_force)
        dprice = to_optional_decimal(price)
        body = {
            "market_id": market_id,
            "side": resolved_side.value,
            "type": otype.value,
            "quantity": int(size),
            "tif": tif.value,
            "post_only": post_only,
            "price": float(dprice) if dprice is not None else None,
        }
        return await self._http.request(
            "POST", "/orders/validate", json=_drop_none(body), auth=True
        )

    # ------------------------------------------------------------------ #
    # Cancellation                                                       #
    # ------------------------------------------------------------------ #
    async def cancel_order(self, order_id: str, *, market: str | None = None) -> Order:
        """Cancel one resting order by engine id.

        ``market`` is inferred from the order id when omitted. Raises
        :class:`OrderRejectedError` if the order is unknown/inactive or not owned by the
        caller.
        """
        market_id = (
            await self._markets.resolve_market_id(market)
            if market
            else market_id_from_order_id(order_id)
        )
        user_id = await self._user_id()
        result = await self._http.request(
            "POST",
            "/cancel_order",
            json={"user_id": user_id, "market_id": market_id, "order_id": order_id},
            auth=True,
        )
        if result.get("status") == "REJECTED":
            reason = result.get("reason")
            raise OrderRejectedError(
                _reason_message(reason, None),
                reason=reason,
                body=result,
            )
        return Order(
            order_id=result.get("order_id", order_id),
            market_id=result.get("market_id", market_id),
            status=result.get("status", "CANCELED"),
            reason=result.get("reason"),
            client_order_id=self._oid_to_coid.get(order_id),
            raw=result,
        )

    async def cancel_order_by_client_id(
        self, client_order_id: str, *, market: str | None = None
    ) -> Order:
        """Cancel an order previously placed with this ``client_order_id``."""
        user_id = await self._user_id()
        order_id = self._coid_to_oid.get((user_id, client_order_id))
        if not order_id:
            raise NotFoundError(
                f"no tracked order for client_order_id {client_order_id!r}",
                code="unknown_client_order_id",
            )
        return await self.cancel_order(order_id, market=market)

    async def cancel_all(self, *, market: str | None = None) -> list[Order]:
        """Cancel every open order (optionally scoped to one market); return the canceled set."""
        open_orders = await self.get_open_orders(market=market, limit=None)
        canceled: list[Order] = []
        for o in open_orders:
            try:
                canceled.append(await self.cancel_order(o.order_id, market=o.market_id))
            except OrderRejectedError:
                # Raced to terminal between the read and the cancel — skip it.
                continue
        return canceled

    async def modify_order(
        self,
        order_id: str,
        *,
        price: PriceLike = None,
        size: int | None = None,
        time_in_force: str | TimeInForce | None = None,
        post_only: bool | None = None,
        client_order_id: str | None = None,
        market: str | None = None,
    ) -> Order:
        """Modify an order via cancel/replace and return the newly placed order.

        The venue has no in-place amend, so this cancels ``order_id`` and submits a new
        order carrying the existing parameters with the supplied overrides applied. If the
        cancel fails (already filled/canceled), the rejection propagates and no new order
        is placed.
        """
        existing = await self.get_order(order_id)
        await self.cancel_order(order_id, market=market or existing.market_id)
        new_price = to_optional_decimal(price) if price is not None else existing.price
        return await self.place_order(
            market=market or existing.market_id,
            side=existing.side or "BUY_YES",
            size=size if size is not None else existing.size,
            price=new_price,
            order_type=existing.order_type,
            time_in_force=time_in_force if time_in_force is not None else existing.time_in_force,
            post_only=post_only if post_only is not None else existing.post_only,
            client_order_id=client_order_id,
        )

    # ------------------------------------------------------------------ #
    # Reads                                                              #
    # ------------------------------------------------------------------ #
    async def get_order(self, order_id: str) -> Order:
        """Fetch a single order by id."""
        market_id = market_id_from_order_id(order_id)
        orders = await self._fetch_orders(market_id=market_id, open_only=False, limit=None)
        for o in orders:
            if o.order_id == order_id:
                return o
        raise NotFoundError(f"order {order_id!r} not found", code="order_not_found")

    async def get_orders(
        self,
        *,
        market: str | None = None,
        open_only: bool = False,
        limit: int | None = 100,
    ) -> list[Order]:
        """List the caller's orders (auto-paginated). ``limit=None`` fetches all pages."""
        market_id = await self._markets.resolve_market_id(market) if market else None
        return await self._fetch_orders(market_id=market_id, open_only=open_only, limit=limit)

    async def get_open_orders(
        self, *, market: str | None = None, limit: int | None = 100
    ) -> list[Order]:
        """List only the caller's resting (open) orders."""
        return await self.get_orders(market=market, open_only=True, limit=limit)

    async def get_order_history(
        self, *, market: str | None = None, limit: int | None = 100
    ) -> list[Order]:
        """List the caller's closed (filled/canceled/rejected) orders."""
        orders = await self.get_orders(market=market, open_only=False, limit=None)
        history = [o for o in orders if o.status in _TERMINAL]
        return history[:limit] if limit is not None else history

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #
    async def _fetch_orders(
        self, *, market_id: str | None, open_only: bool, limit: int | None
    ) -> list[Order]:
        user_id = await self._user_id()

        async def fetch(cursor: str, page_size: int):
            data = await self._http.request(
                "GET",
                "/user/orders",
                params={
                    "user_id": user_id,
                    "market_id": market_id,
                    "open_only": open_only,
                    "limit": page_size,
                    "cursor": cursor,
                },
                auth=True,
            )
            rows = [
                Order.from_api(o, client_order_id=self._oid_to_coid.get(o.get("order_id", "")))
                for o in data.get("orders", [])
            ]
            return rows, data.get("next_cursor", "")

        return await collect_pages(fetch, limit)

    async def _user_id(self) -> str:
        # Ensure we are logged in (sets auth.user_id) then return the account id.
        return await self._auth.require_user_id()

    async def _remember(self, client_order_id: str, order_id: str) -> None:
        user_id = self._auth.user_id or ""
        self._coid_to_oid[(user_id, client_order_id)] = order_id
        self._oid_to_coid[order_id] = client_order_id


def _drop_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def _reason_message(reason: str | None, validation: dict | None) -> str:
    base = {
        "INSUFFICIENT_FUNDS": "insufficient available balance to place this order",
        "MARKET_NOT_OPEN": "market is not open for trading",
        "UNKNOWN_MARKET": "market does not exist",
        "POST_ONLY_WOULD_CROSS": "post-only order would cross the book and take liquidity",
        "POST_ONLY_REQUIRES_LIMIT": "post_only is only valid on LIMIT orders",
        "BELOW_MIN_QUANTITY": "order size is below the market minimum",
        "FOK_UNFILLABLE": "fill-or-kill order could not be fully filled and was killed",
        "INVALID_TICK": "price is not on the allowed tick increment",
        "INVALID_PRICE": "price is outside the allowed range",
        "UNKNOWN_OR_INACTIVE": "order does not exist or is no longer active",
        "NOT_OWNER": "order belongs to a different account",
    }.get((reason or "").upper())
    if base:
        return base
    if validation and isinstance(validation, dict):
        return f"order rejected: {validation.get('reason') or reason or 'unknown reason'}"
    return f"order rejected ({reason or 'unknown reason'})"
