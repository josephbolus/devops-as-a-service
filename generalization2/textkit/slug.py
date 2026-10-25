"""URL slug construction."""
import re

from .normalize import normalize_spaces


def slugify(text):
    """Lowercase slug: alnum runs joined by single hyphens."""
    lowered = normalize_spaces(text).lower()
    return re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
