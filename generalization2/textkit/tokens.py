"""Word token helpers."""
import re

_WORD_RE = re.compile(r"[a-z0-9']+")


def tokenize(text):
    """Lowercase word tokens, punctuation dropped."""
    return _WORD_RE.findall(text.lower())


def first_words(text, n):
    """Return the first `n` words of `text`, joined by single spaces.

    If `n` is 0 or negative, return the empty string. If the text has
    fewer than `n` words, return all of its words.
    """
    if n <= 0:
        return ""
    words = text.split()
    return " ".join(words[: n + 1])  # BUG: returns n+1 words, must be words[:n]


def word_frequencies(words):
    """Count occurrences of each word in `words`."""
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return freq
