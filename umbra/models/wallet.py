"""Wallet models — live on-chain balances and the auth session."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from ..utils.money import to_decimal

__all__ = ["WalletAssets", "UsdcBalance", "Session"]


@dataclass(frozen=True)
class WalletAssets:
    """Live on-chain balances for the authenticated wallet (just-in-time funding).

    ``eth`` and ``usdc`` are human-readable :class:`Decimal` amounts; ``usdc`` is the
    just-in-time buying power gating order admission.
    """

    user_id: str
    wallet_address: str
    eth: Decimal
    usdc: Decimal
    network: dict = field(default_factory=dict)
    token: dict = field(default_factory=dict)
    balances: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_api(cls, data: dict) -> "WalletAssets":
        return cls(
            user_id=data.get("user_id", ""),
            wallet_address=data.get("wallet_address", ""),
            eth=to_decimal(data.get("eth")),
            usdc=to_decimal(data.get("usdc")),
            network=data.get("network") or {},
            token=data.get("token") or {},
            balances=data.get("balances") or {},
            raw=data,
        )


@dataclass(frozen=True)
class UsdcBalance:
    """The wallet's live on-chain USDC balance (the JIT buying power)."""

    user_id: str
    wallet_address: str
    usdc: Decimal
    usdc_units: int
    token: str = "USDC"
    fetched_at: Optional[int] = None
    cached: bool = False
    raw: dict = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_api(cls, data: dict) -> "UsdcBalance":
        return cls(
            user_id=data.get("user_id", ""),
            wallet_address=data.get("wallet_address", ""),
            usdc=to_decimal(data.get("usdc")),
            usdc_units=int(data.get("usdc_units") or 0),
            token=data.get("token", "USDC"),
            fetched_at=data.get("fetched_at"),
            cached=bool(data.get("cached")),
            raw=data,
        )


@dataclass(frozen=True)
class Session:
    """An authenticated session minted by SIWE verification."""

    token: str
    user_id: str
    wallet_address: str
    expires_at: int
    token_type: str = "Bearer"

    @classmethod
    def from_api(cls, data: dict) -> "Session":
        return cls(
            token=data["token"],
            user_id=data.get("user_id", ""),
            wallet_address=data.get("wallet_address", ""),
            expires_at=int(data.get("expires_at") or 0),
            token_type=data.get("token_type", "Bearer"),
        )
