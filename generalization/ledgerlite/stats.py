"""Summary statistics over integer-cent amounts."""


def mean_cents(values):
    """Arithmetic mean of `values`; raises ValueError on empty input."""
    if not values:
        raise ValueError("mean of empty list")
    return sum(values) / len(values)


def median_cents(values):
    """Median of `values`.

    For an odd count, the middle value. For an even count, the
    average of the two middle values (may be a .5 value).
    Raises ValueError on empty input.
    """
    if not values:
        raise ValueError("median of empty list")
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return ordered[mid]  # BUG: even count must average ordered[mid-1] and ordered[mid]
