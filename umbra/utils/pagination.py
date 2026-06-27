"""Cursor pagination helper.

UMBRA list endpoints return ``{... , "next_cursor": "<opaque>"}``; an empty ``next_cursor``
marks the last page. Clients echo the cursor back to fetch the next page. This helper
hides that loop: it keeps fetching pages until it has collected ``limit`` items (or the
server runs out), so a caller can simply ask for ``get_orders(limit=250)`` and get a flat
list spanning as many underlying pages as needed.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

# A page fetcher: given a cursor and a page size, return (items, next_cursor).
PageFetcher = Callable[[str, int], Awaitable[tuple[list[T], str]]]

__all__ = ["collect_pages", "PageFetcher"]

# Largest page the server will serve in one request for the cursor-paginated endpoints.
_MAX_PAGE = 1000


async def collect_pages(
    fetch: PageFetcher[T],
    limit: int | None,
    *,
    start_cursor: str = "",
    max_page: int = _MAX_PAGE,
) -> list[T]:
    """Accumulate items across cursor pages until ``limit`` is reached (or data runs out).

    Parameters
    ----------
    fetch:
        Async callable ``(cursor, page_size) -> (items, next_cursor)``.
    limit:
        Maximum number of items to return. ``None`` fetches every page.
    start_cursor:
        Cursor to begin from (defaults to the first page).
    max_page:
        Per-request page-size ceiling enforced by the server.
    """
    collected: list[T] = []
    cursor = start_cursor
    while True:
        remaining = max_page if limit is None else min(max_page, limit - len(collected))
        if remaining <= 0:
            break
        items, cursor = await fetch(cursor, remaining)
        collected.extend(items)
        if not cursor or not items:
            break
        if limit is not None and len(collected) >= limit:
            break
    if limit is not None:
        return collected[:limit]
    return collected
