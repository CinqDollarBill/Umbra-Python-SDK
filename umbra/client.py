"""The UMBRA client — one object exposing the whole exchange.

Two interchangeable entry points:

* :class:`AsyncUmbraClient` — async-first; every method is a coroutine.
* :class:`UmbraClient` — a synchronous facade that runs the *same* async logic on a
  background event loop, so there is no duplicated business logic and behavior is identical.

Both accept the same constructor arguments and expose the same flat method surface
(``get_markets``, ``place_order``, ``get_positions``, ...). Authentication is handled
transparently: supply wallet credentials (``private_key``, a custom ``signer``, or a
pre-minted ``token``) and the first authenticated call signs in via SIWE and caches the
session.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Union

import httpx

from ._http import AsyncHTTP
from .auth import Authenticator, Signer
from .balances import Balances
from .config import ClientConfig
from .fees import Fees
from .markets import Markets
from .models.common import Account, Nbbo, OrderBook
from .models.fee import FeeEntry, FeeSummary
from .models.market import Market
from .models.order import Order
from .models.position import Position
from .models.trade import Fill, Trade
from .models.wallet import Session, UsdcBalance, WalletAssets
from .orders import Orders, PriceLike
from .positions import Positions
from .trades import Trades
from .types.enums import Category, Outcome, OrderType, Side, TimeInForce
from .utils._sync import LoopRunner
from .websocket import AsyncWebSocketClient, WebSocketClient

__all__ = ["AsyncUmbraClient", "UmbraClient", "Client"]


def _configure_debug_logging() -> None:
    """Attach a stream handler to the ``umbra`` logger at DEBUG (idempotent)."""
    logger = logging.getLogger("umbra")
    logger.setLevel(logging.DEBUG)
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
        logger.addHandler(handler)


class AsyncUmbraClient:
    """Asynchronous UMBRA API client."""

    def __init__(
        self,
        api_url: str,
        *,
        wallet_address: Optional[str] = None,
        private_key: Optional[str] = None,
        signer: Optional[Signer] = None,
        token: Optional[str] = None,
        user_id: Optional[str] = None,
        ws_url: Optional[str] = None,
        timeout: float = 30.0,
        retries: int = 3,
        backoff_factor: float = 0.5,
        backoff_max: float = 10.0,
        debug: bool = False,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        if debug:
            _configure_debug_logging()
        self.config = ClientConfig(
            api_url=api_url, ws_url=ws_url, timeout=timeout, retries=retries,
            backoff_factor=backoff_factor, backoff_max=backoff_max, debug=debug,
        )
        self._http = AsyncHTTP(self.config, transport=transport)
        self.auth = Authenticator(
            self._http,
            wallet_address=wallet_address,
            private_key=private_key,
            signer=signer,
            token=token,
            user_id=user_id,
        )
        self._http.auth = self.auth

        # Resource namespaces (logic lives here; flat methods below delegate to them).
        self.markets = Markets(self._http)
        self.orders = Orders(self._http, self.auth, self.markets)
        self.positions = Positions(self._http, self.auth, self.markets)
        self.balances = Balances(self._http, self.auth)
        self.trades = Trades(self._http, self.auth, self.markets)
        self.fees = Fees(self._http, self.auth, self.markets)

    # ------------------------------------------------------------------ #
    # Lifecycle / identity                                               #
    # ------------------------------------------------------------------ #
    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncUmbraClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def authenticate(self) -> Session:
        """Run SIWE now and return the minted session (otherwise done lazily on first use)."""
        return await self.auth.authenticate()

    async def me(self) -> dict:
        """Return the authenticated account and its login history (``GET /auth/me``)."""
        return await self._http.request("GET", "/auth/me", auth=True)

    @property
    def user_id(self) -> Optional[str]:
        return self.auth.user_id

    @property
    def session(self) -> Optional[Session]:
        return self.auth.session

    # ------------------------------------------------------------------ #
    # Markets                                                            #
    # ------------------------------------------------------------------ #
    async def get_markets(
        self, *, category: Optional[str] = None, status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Market]:
        return await self.markets.list(category=category, status=status, limit=limit)

    async def get_market(self, slug: str, *, with_nbbo: bool = True) -> Market:
        return await self.markets.get(slug, with_nbbo=with_nbbo)

    async def search_markets(self, query: str, *, limit: Optional[int] = None) -> List[Market]:
        return await self.markets.search(query, limit=limit)

    async def get_categories(self) -> List[str]:
        return await self.markets.categories()

    async def get_market_orderbook(self, slug: str) -> OrderBook:
        return await self.markets.orderbook(slug)

    async def get_nbbo(self, slug: str) -> Nbbo:
        return await self.markets.nbbo(slug)

    async def get_crypto_markets(self, *, limit: Optional[int] = None) -> List[Market]:
        return await self.markets.list(category=Category.CRYPTO.value, limit=limit)

    async def get_politics_markets(self, *, limit: Optional[int] = None) -> List[Market]:
        return await self.markets.list(category=Category.POLITICS.value, limit=limit)

    async def get_sports_markets(self, *, limit: Optional[int] = None) -> List[Market]:
        return await self.markets.list(category=Category.SPORTS.value, limit=limit)

    # ------------------------------------------------------------------ #
    # Orders                                                             #
    # ------------------------------------------------------------------ #
    async def place_order(
        self, *, market: str, side: Union[str, Side], size: int,
        outcome: Optional[Union[str, Outcome]] = None, price: PriceLike = None,
        order_type: Union[str, OrderType] = OrderType.LIMIT,
        time_in_force: Union[str, TimeInForce] = TimeInForce.GTC,
        post_only: bool = False, client_order_id: Optional[str] = None,
    ) -> Order:
        return await self.orders.place_order(
            market=market, side=side, size=size, outcome=outcome, price=price,
            order_type=order_type, time_in_force=time_in_force,
            post_only=post_only, client_order_id=client_order_id,
        )

    async def place_limit_order(
        self, *, market: str, side: Union[str, Side], size: int, price: PriceLike,
        outcome: Optional[Union[str, Outcome]] = None,
        time_in_force: Union[str, TimeInForce] = TimeInForce.GTC,
        post_only: bool = False, client_order_id: Optional[str] = None,
    ) -> Order:
        return await self.orders.place_limit_order(
            market=market, side=side, size=size, price=price, outcome=outcome,
            time_in_force=time_in_force, post_only=post_only, client_order_id=client_order_id,
        )

    async def place_market_order(
        self, *, market: str, side: Union[str, Side], size: int,
        outcome: Optional[Union[str, Outcome]] = None,
        time_in_force: Union[str, TimeInForce] = TimeInForce.IOC,
        client_order_id: Optional[str] = None,
    ) -> Order:
        return await self.orders.place_market_order(
            market=market, side=side, size=size, outcome=outcome,
            time_in_force=time_in_force, client_order_id=client_order_id,
        )

    async def validate_order(
        self, *, market: str, side: Union[str, Side], size: int,
        outcome: Optional[Union[str, Outcome]] = None, price: PriceLike = None,
        order_type: Union[str, OrderType] = OrderType.LIMIT,
        time_in_force: Union[str, TimeInForce] = TimeInForce.GTC, post_only: bool = False,
    ) -> dict:
        return await self.orders.validate_order(
            market=market, side=side, size=size, outcome=outcome, price=price,
            order_type=order_type, time_in_force=time_in_force, post_only=post_only,
        )

    async def cancel_order(self, order_id: str, *, market: Optional[str] = None) -> Order:
        return await self.orders.cancel_order(order_id, market=market)

    async def cancel_order_by_client_id(
        self, client_order_id: str, *, market: Optional[str] = None
    ) -> Order:
        return await self.orders.cancel_order_by_client_id(client_order_id, market=market)

    async def cancel_all_orders(self, *, market: Optional[str] = None) -> List[Order]:
        return await self.orders.cancel_all(market=market)

    async def modify_order(
        self, order_id: str, *, price: PriceLike = None, size: Optional[int] = None,
        time_in_force: Optional[Union[str, TimeInForce]] = None,
        post_only: Optional[bool] = None, client_order_id: Optional[str] = None,
        market: Optional[str] = None,
    ) -> Order:
        return await self.orders.modify_order(
            order_id, price=price, size=size, time_in_force=time_in_force,
            post_only=post_only, client_order_id=client_order_id, market=market,
        )

    async def get_order(self, order_id: str) -> Order:
        return await self.orders.get_order(order_id)

    async def get_orders(
        self, *, market: Optional[str] = None, open_only: bool = False,
        limit: Optional[int] = 100,
    ) -> List[Order]:
        return await self.orders.get_orders(market=market, open_only=open_only, limit=limit)

    async def get_open_orders(
        self, *, market: Optional[str] = None, limit: Optional[int] = 100
    ) -> List[Order]:
        return await self.orders.get_open_orders(market=market, limit=limit)

    async def get_order_history(
        self, *, market: Optional[str] = None, limit: Optional[int] = 100
    ) -> List[Order]:
        return await self.orders.get_order_history(market=market, limit=limit)

    # ------------------------------------------------------------------ #
    # Positions                                                          #
    # ------------------------------------------------------------------ #
    async def get_positions(self) -> List[Position]:
        return await self.positions.get_positions()

    async def get_position(self, slug: str) -> Optional[Position]:
        return await self.positions.get_position(slug)

    async def get_account(self) -> Account:
        return await self.positions.get_account()

    # ------------------------------------------------------------------ #
    # Wallet / balances                                                  #
    # ------------------------------------------------------------------ #
    async def get_wallet_assets(self) -> WalletAssets:
        return await self.balances.get_wallet_assets()

    async def get_wallet_balance(self) -> Account:
        return await self.balances.get_wallet_balance()

    async def get_usdc_balance(self) -> UsdcBalance:
        return await self.balances.get_usdc_balance()

    # ------------------------------------------------------------------ #
    # Trades / fills                                                     #
    # ------------------------------------------------------------------ #
    async def get_trades(self, market: str, *, limit: int = 50) -> List[Trade]:
        return await self.trades.get_trades(market, limit=limit)

    async def get_trade(self, trade_id: str, *, market: str) -> Trade:
        return await self.trades.get_trade(trade_id, market=market)

    async def get_fills(
        self, *, market: Optional[str] = None, limit: Optional[int] = 100
    ) -> List[Fill]:
        return await self.trades.get_fills(market=market, limit=limit)

    # ------------------------------------------------------------------ #
    # Fees                                                               #
    # ------------------------------------------------------------------ #
    async def get_fee_history(
        self, *, market: Optional[str] = None, role: Optional[str] = None,
        side: Optional[str] = None, start_ts: Optional[int] = None,
        end_ts: Optional[int] = None, sort: str = "-ts", limit: Optional[int] = 100,
    ) -> List[FeeEntry]:
        return await self.fees.get_fee_history(
            market=market, role=role, side=side, start_ts=start_ts, end_ts=end_ts,
            sort=sort, limit=limit,
        )

    async def get_fee_summary(
        self, *, market: Optional[str] = None, role: Optional[str] = None,
        side: Optional[str] = None, start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
    ) -> FeeSummary:
        return await self.fees.get_fee_summary(
            market=market, role=role, side=side, start_ts=start_ts, end_ts=end_ts
        )

    async def get_trade_fees(self, trade_id: str) -> List[FeeEntry]:
        return await self.fees.get_trade_fees(trade_id)

    # ------------------------------------------------------------------ #
    # WebSocket                                                          #
    # ------------------------------------------------------------------ #
    def websocket(self) -> AsyncWebSocketClient:
        """Create a real-time WebSocket client bound to this session."""
        return AsyncWebSocketClient(self.config, self.auth, self.markets)


class UmbraClient:
    """Synchronous UMBRA API client (a thin facade over :class:`AsyncUmbraClient`)."""

    def __init__(self, api_url: str, **kwargs: Any) -> None:
        self._runner = LoopRunner()
        # Construct the async client on the background loop so all loop-bound state
        # (httpx pool, locks) lives on the thread it will run on.
        self._aio: AsyncUmbraClient = self._runner.run(self._build(api_url, kwargs))

    @staticmethod
    async def _build(api_url: str, kwargs: dict) -> AsyncUmbraClient:
        return AsyncUmbraClient(api_url, **kwargs)

    def _run(self, coro: Any) -> Any:
        return self._runner.run(coro)

    # ------------------------------------------------------------------ #
    # Lifecycle / identity                                               #
    # ------------------------------------------------------------------ #
    def close(self) -> None:
        """Close the client and stop the background event loop."""
        try:
            self._run(self._aio.aclose())
        finally:
            self._runner.close()

    def __enter__(self) -> "UmbraClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def authenticate(self) -> Session:
        return self._run(self._aio.authenticate())

    def me(self) -> dict:
        return self._run(self._aio.me())

    @property
    def user_id(self) -> Optional[str]:
        return self._aio.user_id

    @property
    def session(self) -> Optional[Session]:
        return self._aio.session

    # ------------------------------------------------------------------ #
    # Markets                                                            #
    # ------------------------------------------------------------------ #
    def get_markets(
        self, *, category: Optional[str] = None, status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Market]:
        return self._run(self._aio.get_markets(category=category, status=status, limit=limit))

    def get_market(self, slug: str, *, with_nbbo: bool = True) -> Market:
        return self._run(self._aio.get_market(slug, with_nbbo=with_nbbo))

    def search_markets(self, query: str, *, limit: Optional[int] = None) -> List[Market]:
        return self._run(self._aio.search_markets(query, limit=limit))

    def get_categories(self) -> List[str]:
        return self._run(self._aio.get_categories())

    def get_market_orderbook(self, slug: str) -> OrderBook:
        return self._run(self._aio.get_market_orderbook(slug))

    def get_nbbo(self, slug: str) -> Nbbo:
        return self._run(self._aio.get_nbbo(slug))

    def get_crypto_markets(self, *, limit: Optional[int] = None) -> List[Market]:
        return self._run(self._aio.get_crypto_markets(limit=limit))

    def get_politics_markets(self, *, limit: Optional[int] = None) -> List[Market]:
        return self._run(self._aio.get_politics_markets(limit=limit))

    def get_sports_markets(self, *, limit: Optional[int] = None) -> List[Market]:
        return self._run(self._aio.get_sports_markets(limit=limit))

    # ------------------------------------------------------------------ #
    # Orders                                                             #
    # ------------------------------------------------------------------ #
    def place_order(
        self, *, market: str, side: Union[str, Side], size: int,
        outcome: Optional[Union[str, Outcome]] = None, price: PriceLike = None,
        order_type: Union[str, OrderType] = OrderType.LIMIT,
        time_in_force: Union[str, TimeInForce] = TimeInForce.GTC,
        post_only: bool = False, client_order_id: Optional[str] = None,
    ) -> Order:
        return self._run(self._aio.place_order(
            market=market, side=side, size=size, outcome=outcome, price=price,
            order_type=order_type, time_in_force=time_in_force,
            post_only=post_only, client_order_id=client_order_id,
        ))

    def place_limit_order(
        self, *, market: str, side: Union[str, Side], size: int, price: PriceLike,
        outcome: Optional[Union[str, Outcome]] = None,
        time_in_force: Union[str, TimeInForce] = TimeInForce.GTC,
        post_only: bool = False, client_order_id: Optional[str] = None,
    ) -> Order:
        return self._run(self._aio.place_limit_order(
            market=market, side=side, size=size, price=price, outcome=outcome,
            time_in_force=time_in_force, post_only=post_only, client_order_id=client_order_id,
        ))

    def place_market_order(
        self, *, market: str, side: Union[str, Side], size: int,
        outcome: Optional[Union[str, Outcome]] = None,
        time_in_force: Union[str, TimeInForce] = TimeInForce.IOC,
        client_order_id: Optional[str] = None,
    ) -> Order:
        return self._run(self._aio.place_market_order(
            market=market, side=side, size=size, outcome=outcome,
            time_in_force=time_in_force, client_order_id=client_order_id,
        ))

    def validate_order(
        self, *, market: str, side: Union[str, Side], size: int,
        outcome: Optional[Union[str, Outcome]] = None, price: PriceLike = None,
        order_type: Union[str, OrderType] = OrderType.LIMIT,
        time_in_force: Union[str, TimeInForce] = TimeInForce.GTC, post_only: bool = False,
    ) -> dict:
        return self._run(self._aio.validate_order(
            market=market, side=side, size=size, outcome=outcome, price=price,
            order_type=order_type, time_in_force=time_in_force, post_only=post_only,
        ))

    def cancel_order(self, order_id: str, *, market: Optional[str] = None) -> Order:
        return self._run(self._aio.cancel_order(order_id, market=market))

    def cancel_order_by_client_id(
        self, client_order_id: str, *, market: Optional[str] = None
    ) -> Order:
        return self._run(self._aio.cancel_order_by_client_id(client_order_id, market=market))

    def cancel_all_orders(self, *, market: Optional[str] = None) -> List[Order]:
        return self._run(self._aio.cancel_all_orders(market=market))

    def modify_order(
        self, order_id: str, *, price: PriceLike = None, size: Optional[int] = None,
        time_in_force: Optional[Union[str, TimeInForce]] = None,
        post_only: Optional[bool] = None, client_order_id: Optional[str] = None,
        market: Optional[str] = None,
    ) -> Order:
        return self._run(self._aio.modify_order(
            order_id, price=price, size=size, time_in_force=time_in_force,
            post_only=post_only, client_order_id=client_order_id, market=market,
        ))

    def get_order(self, order_id: str) -> Order:
        return self._run(self._aio.get_order(order_id))

    def get_orders(
        self, *, market: Optional[str] = None, open_only: bool = False,
        limit: Optional[int] = 100,
    ) -> List[Order]:
        return self._run(self._aio.get_orders(market=market, open_only=open_only, limit=limit))

    def get_open_orders(
        self, *, market: Optional[str] = None, limit: Optional[int] = 100
    ) -> List[Order]:
        return self._run(self._aio.get_open_orders(market=market, limit=limit))

    def get_order_history(
        self, *, market: Optional[str] = None, limit: Optional[int] = 100
    ) -> List[Order]:
        return self._run(self._aio.get_order_history(market=market, limit=limit))

    # ------------------------------------------------------------------ #
    # Positions                                                          #
    # ------------------------------------------------------------------ #
    def get_positions(self) -> List[Position]:
        return self._run(self._aio.get_positions())

    def get_position(self, slug: str) -> Optional[Position]:
        return self._run(self._aio.get_position(slug))

    def get_account(self) -> Account:
        return self._run(self._aio.get_account())

    # ------------------------------------------------------------------ #
    # Wallet / balances                                                  #
    # ------------------------------------------------------------------ #
    def get_wallet_assets(self) -> WalletAssets:
        return self._run(self._aio.get_wallet_assets())

    def get_wallet_balance(self) -> Account:
        return self._run(self._aio.get_wallet_balance())

    def get_usdc_balance(self) -> UsdcBalance:
        return self._run(self._aio.get_usdc_balance())

    # ------------------------------------------------------------------ #
    # Trades / fills                                                     #
    # ------------------------------------------------------------------ #
    def get_trades(self, market: str, *, limit: int = 50) -> List[Trade]:
        return self._run(self._aio.get_trades(market, limit=limit))

    def get_trade(self, trade_id: str, *, market: str) -> Trade:
        return self._run(self._aio.get_trade(trade_id, market=market))

    def get_fills(
        self, *, market: Optional[str] = None, limit: Optional[int] = 100
    ) -> List[Fill]:
        return self._run(self._aio.get_fills(market=market, limit=limit))

    # ------------------------------------------------------------------ #
    # Fees                                                               #
    # ------------------------------------------------------------------ #
    def get_fee_history(
        self, *, market: Optional[str] = None, role: Optional[str] = None,
        side: Optional[str] = None, start_ts: Optional[int] = None,
        end_ts: Optional[int] = None, sort: str = "-ts", limit: Optional[int] = 100,
    ) -> List[FeeEntry]:
        return self._run(self._aio.get_fee_history(
            market=market, role=role, side=side, start_ts=start_ts, end_ts=end_ts,
            sort=sort, limit=limit,
        ))

    def get_fee_summary(
        self, *, market: Optional[str] = None, role: Optional[str] = None,
        side: Optional[str] = None, start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
    ) -> FeeSummary:
        return self._run(self._aio.get_fee_summary(
            market=market, role=role, side=side, start_ts=start_ts, end_ts=end_ts
        ))

    def get_trade_fees(self, trade_id: str) -> List[FeeEntry]:
        return self._run(self._aio.get_trade_fees(trade_id))

    # ------------------------------------------------------------------ #
    # WebSocket                                                          #
    # ------------------------------------------------------------------ #
    def websocket(self) -> WebSocketClient:
        """Create a synchronous real-time WebSocket client bound to this session."""
        async_ws = self._run(self._new_ws())
        return WebSocketClient(async_ws, self._run)

    async def _new_ws(self) -> AsyncWebSocketClient:
        # Construct on the background loop so its asyncio.Queue binds to the right loop.
        return self._aio.websocket()


# The primary, recommended entry point is the synchronous client.
Client = UmbraClient
