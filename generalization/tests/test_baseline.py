import unittest

from ledgerlite.amounts import format_cents, parse_cents
from ledgerlite.entries import Entry, filter_by_tag, total_cents
from ledgerlite.report import summarize
from ledgerlite.stats import mean_cents, median_cents


class AmountsBaseline(unittest.TestCase):
    def test_parse_whole_and_fractional(self):
        self.assertEqual(parse_cents("12.34"), 1234)
        self.assertEqual(parse_cents("7"), 700)

    def test_parse_negative(self):
        self.assertEqual(parse_cents("-3.05"), -305)

    def test_format(self):
        self.assertEqual(format_cents(1234), "12.34")
        self.assertEqual(format_cents(-305), "-3.05")


class EntriesBaseline(unittest.TestCase):
    def test_total(self):
        entries = [Entry("a", 100), Entry("b", 250)]
        self.assertEqual(total_cents(entries), 350)

    def test_filter_by_tag(self):
        entries = [Entry("a", 100, "food"), Entry("b", 250, "rent"),
                   Entry("c", 50, "food")]
        self.assertEqual([e.label for e in filter_by_tag(entries, "food")],
                         ["a", "c"])


class StatsBaseline(unittest.TestCase):
    def test_mean(self):
        self.assertEqual(mean_cents([100, 200, 300]), 200.0)

    def test_median_odd_count(self):
        self.assertEqual(median_cents([300, 100, 200]), 200)

    def test_median_single_and_empty(self):
        self.assertEqual(median_cents([42]), 42)
        with self.assertRaises(ValueError):
            median_cents([])


class ReportBaseline(unittest.TestCase):
    def test_summarize_shape(self):
        out = summarize([Entry("a", 100), Entry("b", 200), Entry("c", 300)])
        self.assertIn("entries: 3", out)
        self.assertIn("total: 6.00", out)


if __name__ == "__main__":
    unittest.main()
