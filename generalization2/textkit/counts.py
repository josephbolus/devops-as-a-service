"""Reading statistics over raw text."""
from .tokens import tokenize


def count_sentences(text):
    """Count sentence-ending punctuation marks (. ! ?)."""
    return sum(text.count(c) for c in ".!?")


def reading_minutes(text, wpm=200):
    """Estimated reading time in minutes at `wpm` words per minute."""
    return len(tokenize(text)) / wpm
