"""A one-line human summary of a list of entries."""
from .amounts import format_cents
from .entries import total_cents
from .stats import mean_cents, median_cents


def summarize(entries):
    values = [e.cents for e in entries]
    if not values:
        return "entries: 0  total: 0.00"
    return (
        f"entries: {len(values)}  total: {format_cents(total_cents(entries))}  "
        f"mean: {format_cents(int(round(mean_cents(values))))}  "
        f"median: {format_cents(int(round(float(median_cents(values)))))}"
    )
