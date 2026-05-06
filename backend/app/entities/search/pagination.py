import math
from typing import TypeVar

T = TypeVar("T")


def paginate_results(
    results: list[T],
    page: int,
    per_page: int,
) -> tuple[list[T], int]:
    """Slice a pre-fetched ordered list into a single page and compute total_pages.

    Returns (page_slice, total_pages).
    total_pages is always >= 1 — returning 0 for an empty list breaks pagination UIs.
    A page beyond the end returns an empty slice, not an error.
    """
    total = len(results)
    total_pages = max(1, math.ceil(total / per_page))
    offset = (page - 1) * per_page
    return results[offset : offset + per_page], total_pages
