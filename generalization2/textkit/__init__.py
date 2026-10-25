"""textkit — tiny text utilities (stdlib only)."""
from .counts import count_sentences, reading_minutes
from .normalize import normalize_spaces, title_key
from .slug import slugify
from .tokens import first_words, tokenize, word_frequencies

__all__ = ["count_sentences", "first_words", "normalize_spaces",
           "reading_minutes", "slugify", "title_key", "tokenize",
           "word_frequencies"]
