"""Whitespace and case normalization helpers."""


def normalize_spaces(text):
    """Collapse every run of whitespace to a single space and strip."""
    return " ".join(text.split())


def title_key(text):
    """A comparison key: whitespace-normalized and lowercased."""
    return normalize_spaces(text).lower()
