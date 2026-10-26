"""Client for an upstream API that paginates its list responses.

Expansion seed issue #11 (dependency/API compatibility, intentional
— do not fix in the scaffold): the upstream API used to return every
item in one response, so fetch_all() reads a single page. The
upstream now paginates: each response carries a "next_page" cursor,
and fetch_all() silently returns only the first page's items, so
callers see a truncated list and downstream counts are wrong.
"""


def fetch_all(fetch_page):
    """Return every item from the paginated upstream, in page order.

    `fetch_page(page)` (1-indexed) returns
    {"items": [...], "next_page": <int or None>}. Follow next_page
    until it is None and concatenate all pages' items.
    """
    first = fetch_page(1)
    # BUG: only the first page is returned — next_page is ignored, so
    # every item past page 1 is silently dropped.
    return list(first["items"])
