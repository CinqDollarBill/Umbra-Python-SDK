"""Client configuration for the UMBRA SDK.

:class:`ClientConfig` centralizes every tunable so nothing is hardcoded: the API base
URL, derived WebSocket URL, request timeout, retry policy, and debug logging. The
:class:`~umbra.client.UmbraClient` / :class:`~umbra.client.AsyncUmbraClient` accept the
same keyword arguments and build a :class:`ClientConfig` from them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .exceptions import ConfigurationError

__all__ = ["ClientConfig", "DEFAULT_TIMEOUT", "DEFAULT_RETRIES"]

DEFAULT_TIMEOUT: float = 30.0
DEFAULT_RETRIES: int = 3
_DEFAULT_USER_AGENT = "umbra-python-sdk/0.1.0"


def _derive_ws_url(api_url: str) -> str:
    """Derive the WebSocket base URL from the REST base URL (http->ws, https->wss)."""
    if api_url.startswith("https://"):
        return "wss://" + api_url[len("https://") :]
    if api_url.startswith("http://"):
        return "ws://" + api_url[len("http://") :]
    # Already a ws/wss URL, or a bare host — leave it to the caller.
    return api_url


@dataclass
class ClientConfig:
    """Immutable-ish configuration shared by the REST and WebSocket clients.

    Parameters
    ----------
    api_url:
        Base REST URL, e.g. ``"https://api.umbra.exchange"`` or ``"http://localhost:8000"``.
        Required; never hardcoded by the SDK.
    ws_url:
        Base WebSocket URL. Defaults to ``api_url`` with the scheme mapped to ``ws``/``wss``.
    timeout:
        Per-request timeout in seconds.
    retries:
        Maximum automatic retries for transient failures (network errors, ``5xx``, ``429``).
        Invalid user requests (``4xx`` other than ``429``) are never retried.
    backoff_factor:
        Base for the exponential backoff between retries (seconds): the n-th retry waits
        roughly ``backoff_factor * 2 ** n`` seconds (plus jitter), capped by ``backoff_max``.
    backoff_max:
        Upper bound on a single backoff sleep, in seconds.
    debug:
        When ``True``, the SDK emits request/response debug logs on the ``umbra`` logger
        (auth headers are redacted).
    user_agent:
        Value sent in the ``User-Agent`` header.
    """

    api_url: str
    ws_url: str | None = None
    timeout: float = DEFAULT_TIMEOUT
    retries: int = DEFAULT_RETRIES
    backoff_factor: float = 0.5
    backoff_max: float = 10.0
    debug: bool = False
    user_agent: str = _DEFAULT_USER_AGENT
    default_headers: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.api_url or not isinstance(self.api_url, str):
            raise ConfigurationError("api_url is required (e.g. 'https://api.umbra.exchange')")
        self.api_url = self.api_url.rstrip("/")
        if self.ws_url is None:
            self.ws_url = _derive_ws_url(self.api_url)
        self.ws_url = self.ws_url.rstrip("/")
        if self.timeout <= 0:
            raise ConfigurationError("timeout must be positive")
        if self.retries < 0:
            raise ConfigurationError("retries must be >= 0")
