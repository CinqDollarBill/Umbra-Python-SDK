"""Async HTTP transport — retries, error mapping, auth injection, debug logging.

This is the single place the SDK talks HTTP. Resource modules describe *what* to call
(method, path, params, body, whether auth is needed); this layer handles *how*:

* injects the bearer token from the :class:`~umbra.auth.Authenticator` when auth is required
  (and transparently re-authenticates once on a ``401``);
* retries transient failures (network errors, ``429``, ``5xx``) with exponential backoff +
  jitter, while never retrying an invalid user request — and never unsafely retrying a
  non-idempotent ``POST``;
* translates every non-2xx response into a typed :mod:`umbra.exceptions` error, so raw
  ``httpx`` errors never reach SDK users;
* emits redacted request/response logs when ``debug=True``.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING, Any

import httpx

from .config import ClientConfig
from .exceptions import (
    APIError,
    AuthenticationError,
    NetworkError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    ValidationError,
)

if TYPE_CHECKING:  # pragma: no cover
    from .auth import Authenticator

logger = logging.getLogger("umbra")

_IDEMPOTENT_METHODS = {"GET", "HEAD", "OPTIONS", "DELETE"}
_RETRY_STATUSES = {500, 502, 503, 504}


class AsyncHTTP:
    """Async transport over a single ``httpx.AsyncClient``."""

    def __init__(
        self,
        config: ClientConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        headers = {
            "User-Agent": config.user_agent,
            "Accept": "application/json",
            **config.default_headers,
        }
        self._client = httpx.AsyncClient(
            base_url=config.api_url,
            timeout=config.timeout,
            headers=headers,
            transport=transport,
        )
        # Set by the owning client once the Authenticator is constructed (avoids a cycle).
        self.auth: Authenticator | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #
    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------ #
    # Core request                                                       #
    # ------------------------------------------------------------------ #
    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: Any = None,
        auth: bool = False,
        idempotent: bool | None = None,
        _reauthed: bool = False,
    ) -> Any:
        """Perform an HTTP request and return the decoded JSON body.

        Parameters
        ----------
        auth:
            When ``True``, attach the authenticated bearer token (authenticating via SIWE
            on first use if necessary).
        idempotent:
            Whether the request is safe to retry after the server may have received it.
            Defaults to ``True`` for GET/DELETE and ``False`` for POST. The resource layer
            passes ``True`` for a POST carrying a ``client_order_id`` (idempotency key).
        """
        method = method.upper()
        if idempotent is None:
            idempotent = method in _IDEMPOTENT_METHODS

        headers = {}
        if auth:
            token = await self._require_token()
            headers["Authorization"] = f"Bearer {token}"

        clean_params = _drop_none(params)
        attempt = 0
        while True:
            self._log_request(method, path, clean_params, json, attempt)
            try:
                response = await self._client.request(
                    method, path, params=clean_params, json=json, headers=headers
                )
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                # Request was never delivered — always safe to retry.
                if attempt < self._config.retries:
                    await self._sleep_backoff(attempt)
                    attempt += 1
                    continue
                raise NetworkError(
                    f"could not connect to {self._config.api_url}", cause=exc
                ) from exc
            except httpx.TimeoutException as exc:
                # Response timed out — only safe to retry idempotent calls.
                if idempotent and attempt < self._config.retries:
                    await self._sleep_backoff(attempt)
                    attempt += 1
                    continue
                raise NetworkError(f"request to {path} timed out", cause=exc) from exc
            except httpx.HTTPError as exc:
                raise NetworkError(f"transport error calling {path}: {exc}", cause=exc) from exc

            status = response.status_code
            self._log_response(method, path, status)

            if 200 <= status < 300:
                return _decode(response)

            # Re-authenticate once on a 401 for an authed request (token may have expired).
            if status == 401 and auth and not _reauthed and self.auth is not None:
                self.auth.invalidate()
                return await self.request(
                    method,
                    path,
                    params=params,
                    json=json,
                    auth=auth,
                    idempotent=idempotent,
                    _reauthed=True,
                )

            if status == 429:
                retry_after = _retry_after_seconds(response)
                if attempt < self._config.retries:
                    await self._sleep_backoff(attempt, override=retry_after)
                    attempt += 1
                    continue

            if status in _RETRY_STATUSES and idempotent and attempt < self._config.retries:
                await self._sleep_backoff(attempt)
                attempt += 1
                continue

            raise self._error_for(method, path, response)

    # ------------------------------------------------------------------ #
    # Auth                                                               #
    # ------------------------------------------------------------------ #
    async def _require_token(self) -> str:
        if self.auth is None or not self.auth.can_authenticate:
            raise AuthenticationError(
                "this call requires authentication; construct the client with credentials "
                "(wallet_address + private_key, a custom signer, or token=...)"
            )
        return await self.auth.token()

    # ------------------------------------------------------------------ #
    # Error translation                                                  #
    # ------------------------------------------------------------------ #
    def _error_for(self, method: str, path: str, response: httpx.Response) -> APIError:
        status = response.status_code
        body = _safe_body(response)
        code, message, detail = _extract_error(body, status)
        kw = dict(
            status_code=status, code=code, body=body, request_method=method, request_path=path
        )
        if status == 401:
            return AuthenticationError(message, **kw)  # type: ignore[arg-type]
        if status == 403:
            return PermissionError(message, **kw)  # type: ignore[arg-type]
        if status == 404:
            return NotFoundError(message, **kw)  # type: ignore[arg-type]
        if status == 422:
            return ValidationError(message, errors=detail, **kw)  # type: ignore[arg-type]
        if status == 429:
            return RateLimitError(
                message, retry_after=_retry_after_seconds(response), **kw  # type: ignore[arg-type]
            )
        return APIError(message, **kw)  # type: ignore[arg-type]

    # ------------------------------------------------------------------ #
    # Backoff + logging                                                  #
    # ------------------------------------------------------------------ #
    async def _sleep_backoff(self, attempt: int, *, override: float | None = None) -> None:
        if override is not None:
            delay = min(override, self._config.backoff_max)
        else:
            base = self._config.backoff_factor * (2**attempt)
            delay = min(base, self._config.backoff_max)
            delay += random.uniform(0, self._config.backoff_factor)  # jitter
        if self._config.debug:
            logger.debug("umbra: retrying after %.2fs (attempt %d)", delay, attempt + 1)
        await asyncio.sleep(delay)

    def _log_request(self, method: str, path: str, params: Any, json: Any, attempt: int) -> None:
        if not self._config.debug:
            return
        suffix = f" (retry {attempt})" if attempt else ""
        logger.debug("umbra -> %s %s params=%s json=%s%s", method, path, params, json, suffix)

    def _log_response(self, method: str, path: str, status: int) -> None:
        if not self._config.debug:
            return
        logger.debug("umbra <- %s %s %s", status, method, path)


# --------------------------------------------------------------------------- #
# Module-level helpers.                                                        #
# --------------------------------------------------------------------------- #
def _drop_none(params: dict | None) -> dict | None:
    """Strip ``None`` values so they aren't serialized as the string ``"None"``."""
    if not params:
        return None
    return {k: v for k, v in params.items() if v is not None}


def _decode(response: httpx.Response) -> Any:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text


def _safe_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _extract_error(body: Any, status: int) -> tuple[str | None, str, Any]:
    """Return ``(code, message, detail)`` from a non-2xx body across the API's shapes.

    Handles FastAPI ``{"detail": ...}`` (string or validation list), the ``/v1`` envelope
    ``{"error": {"code", "message"}}``, and the sanitized 500 ``{"error": {...}}``.
    """
    code: str | None = None
    detail: Any = None
    message = f"HTTP {status}"
    if isinstance(body, dict):
        if isinstance(body.get("error"), dict):
            err = body["error"]
            code = err.get("code")
            message = err.get("message") or message
        elif "detail" in body:
            detail = body["detail"]
            if isinstance(detail, str):
                message = detail
                code = detail if detail.isupper() else None
            elif isinstance(detail, list) and detail:
                msgs = [d.get("msg", "") for d in detail if isinstance(d, dict)]
                message = "; ".join(m for m in msgs if m) or message
        elif "message" in body:
            message = str(body["message"])
            code = body.get("code")
    elif isinstance(body, str) and body:
        message = body
    return code, message, detail


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None
