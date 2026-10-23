"""Pagination helper.

KNOWN BUG (Tier-1 seed issue, intentional — do not fix in the scaffold):
when the total is an exact multiple of the page size, the last page
comes back one item short. 20 items, page size 10, page 2 -> 9 items.
"""


def paginate(items, page, page_size):
    """Return the 1-indexed `page` of `items`, `page_size` per page."""
    if page < 1:
        raise ValueError("page is 1-indexed and must be >= 1")
    if page_size < 1:
        raise ValueError("page_size must be >= 1")
    start = (page - 1) * page_size
    end = start + page_size
    return items[start : end - 1]  # BUG: the -1 drops the last item of full pages
