"""Ledger entries and simple aggregations over them."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    label: str
    cents: int
    tag: str = "misc"


def total_cents(entries):
    return sum(e.cents for e in entries)


def filter_by_tag(entries, tag):
    return [e for e in entries if e.tag == tag]
