import unittest

from gradebook.averages import simple_mean, weighted_mean
from gradebook.letters import grade_points, letter_grade
from gradebook.report import final_letter, summarize


class AveragesBaseline(unittest.TestCase):
    def test_simple_mean_basic(self):
        self.assertEqual(simple_mean([80, 90, 100]), 90.0)

    def test_simple_mean_empty(self):
        self.assertEqual(simple_mean([]), 0.0)

    def test_weighted_mean_unit_weights(self):
        # Weights of 1: sum(weights) == len(values), so this passes
        # whether or not the denominator is the weight total.
        self.assertEqual(weighted_mean([80, 100], [1, 1]), 90.0)
        self.assertEqual(weighted_mean([70, 80, 90], [1, 1, 1]), 80.0)

    def test_weighted_mean_zero_total_weight(self):
        self.assertEqual(weighted_mean([80, 100], [0, 0]), 0.0)

    def test_weighted_mean_empty(self):
        self.assertEqual(weighted_mean([], []), 0.0)


class LettersBaseline(unittest.TestCase):
    def test_letter_grade_bands(self):
        self.assertEqual(letter_grade(95), "A")
        self.assertEqual(letter_grade(85), "B")
        self.assertEqual(letter_grade(72), "C")
        self.assertEqual(letter_grade(60), "D")
        self.assertEqual(letter_grade(42), "F")

    def test_letter_grade_just_below_a(self):
        self.assertEqual(letter_grade(89), "B")

    def test_grade_points(self):
        self.assertEqual(grade_points("A"), 4)
        self.assertEqual(grade_points("F"), 0)


class ReportBaseline(unittest.TestCase):
    def test_final_letter_clear_a(self):
        self.assertEqual(final_letter([100, 90], [1, 1]), "A")

    def test_final_letter_clear_b(self):
        self.assertEqual(final_letter([80, 90], [1, 1]), "B")

    def test_summarize(self):
        self.assertEqual(summarize([80, 90], [1, 1]),
                         {"mean": 85.0, "letter": "B"})

    def test_summarize_empty(self):
        self.assertEqual(summarize([], []), {"mean": 0.0, "letter": "F"})


if __name__ == "__main__":
    unittest.main()
