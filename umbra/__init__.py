"""UMBRA — official Python SDK.

Install the SDK, authenticate with your wallet, and place your first trade in a few lines::

    from umbra import Client

    client = Client(
        api_url="https://api.umbra.exchange",
        private_key="0x...",          # signs the SIWE login locally
    )

    for market in client.get_crypto_markets():
        print(market.slug, market.title)

    order = client.place_limit_order(
        market="btc-updown-5m",
        side="BUY", outcome="YES",
        price="0.62", size=1000,
    )
    print(order.order_id, order.status)

Prefer ``async``? Use :class:`AsyncUmbraClient` with the identical method surface::

    from umbra import AsyncUmbraClient

    async with AsyncUmbraClient(api_url="...", private_key="0x...") as client:
        nbbo = await client.get_nbbo("btc-updown-5m")
"""

from __future__ import annotations

from .auth import Authenticator
from .client import AsyncUmbraClient, Client, UmbraClient
from .config import ClientConfig
from .exceptions import (
    APIError,
    AuthenticationError,
    ConfigurationError,
    InsufficientFundsError,
    MarketClosedError,
    NetworkError,
    NotFoundError,
    OrderRejectedError,
    PermissionError,
    RateLimitError,
    UmbraError,
    ValidationError,
    WebSocketError,
)
from .models import (
    Account,
    BookLevel,
    FeeEntry,
    FeeSummary,
    Fill,
    Market,
    Nbbo,
    Order,
    OrderBook,
    Page,
    Position,
    Session,
    Token,
    Trade,
    UsdcBalance,
    WalletAssets,
)
from .types import (
    Category,
    MarketStatus,
    OrderStatus,
    OrderType,
    Outcome,
    Side,
    TimeInForce,
    resolve_side,
)
from .websocket import AsyncWebSocketClient, WebSocketClient

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # Clients
    "Client",
    "UmbraClient",
    "AsyncUmbraClient",
    "ClientConfig",
    "Authenticator",
    # WebSocket
    "AsyncWebSocketClient",
    "WebSocketClient",
    # Enums
    "Side",
    "Outcome",
    "OrderType",
    "TimeInForce",
    "OrderStatus",
    "MarketStatus",
    "Category",
    "resolve_side",
    # Models
    "Market",
    "Token",
    "Nbbo",
    "OrderBook",
    "BookLevel",
    "Order",
    "Position",
    "Trade",
    "Fill",
    "FeeEntry",
    "FeeSummary",
    "Account",
    "WalletAssets",
    "UsdcBalance",
    "Session",
    "Page",
    # Exceptions
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
