import unittest

from textkit.counts import count_sentences, reading_minutes
from textkit.normalize import normalize_spaces, title_key
from textkit.slug import slugify
from textkit.tokens import first_words, tokenize, word_frequencies


class NormalizeBaseline(unittest.TestCase):
    def test_normalize_spaces_collapses(self):
        self.assertEqual(normalize_spaces("  a \t b\n c "), "a b c")

    def test_title_key_lowercases(self):
        self.assertEqual(title_key("  Hello   WORLD "), "hello world")


class TokensBaseline(unittest.TestCase):
    def test_tokenize_drops_punctuation(self):
        self.assertEqual(tokenize("Hello, World!"), ["hello", "world"])

    def test_word_frequencies(self):
        self.assertEqual(word_frequencies(["a", "b", "a"]), {"a": 2, "b": 1})

    def test_first_words_limit_exceeds_length(self):
        self.assertEqual(first_words("alpha beta", 5), "alpha beta")

    def test_first_words_zero_and_empty(self):
        self.assertEqual(first_words("alpha beta", 0), "")
        self.assertEqual(first_words("", 3), "")


class SlugBaseline(unittest.TestCase):
    def test_slugify_basic(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_slugify_collapses_separators(self):
        self.assertEqual(slugify("a -- b!! c"), "a-b-c")


class CountsBaseline(unittest.TestCase):
    def test_count_sentences(self):
        self.assertEqual(count_sentences("One. Two! Three?"), 3)

    def test_reading_minutes(self):
        self.assertEqual(reading_minutes("word " * 100), 0.5)


if __name__ == "__main__":
    unittest.main()
