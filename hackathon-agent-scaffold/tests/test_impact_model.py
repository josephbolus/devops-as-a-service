"""Pin the impact model (repo-root IMPACT_MODEL.md).

The model is a judged Impact artifact: it must stay honestly labeled
(a model, not a measured result), source every input, and its tables
must match the arithmetic recomputed here from the stated inputs —
a changed input that is not carried through fails this suite.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "IMPACT_MODEL.md"

MANUAL_MIN = 60
REVIEW_MIN = 10
SAVED_MIN = MANUAL_MIN - REVIEW_MIN


def fmt_hours(minutes):
    return minutes / 60.0


class TestImpactModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_honest_labeling(self):
        self.assertIn("This is a model, not a measured result", self.text)
        self.assertIn("No real users yet", self.text)
        self.assertIn("timed 3/3 live eval", self.text)
        self.assertIn("No dollar saving is claimed", self.text)

    def test_inputs_are_labeled_and_sourced(self):
        for token in ("measured", "entry assertion", "model assumption",
                      "five-engineer", "PR #16", "6 → 8",
                      "eval-scorecard/SCORECARD.md"):
            self.assertIn(token, self.text, token)

    def test_scope_is_limited_to_passed_small_issues(self):
        self.assertIn("passing the deterministic guardrail", self.text)
        self.assertIn("Escalated issues are excluded", self.text)
        self.assertIn("per **passed** issue", self.text)

    def test_primary_grid_arithmetic(self):
        self.assertEqual(SAVED_MIN, 50)
        for b in (3, 5, 10):
            weekly = b * SAVED_MIN
            for token in (f"{fmt_hours(weekly):.2f} h",
                          f"{fmt_hours(weekly * 4):.1f} h",
                          f"{fmt_hours(weekly * 52):.1f} h"):
                self.assertIn(token, self.text, (b, token))

    def test_review_sensitivity_arithmetic(self):
        for review in (5, 10, 20, 30):
            saved = MANUAL_MIN - review
            self.assertIn(f"{saved} min", self.text, review)
            self.assertIn(f"{fmt_hours(5 * saved):.2f} h", self.text, review)
        self.assertIn("break-even is 60 min", self.text)

    def test_measurement_plan_replaces_assumptions(self):
        self.assertIn("How to replace this model with measurements",
                      self.text)
        for token in ("Time the review", "Audit a real backlog",
                      "Measure the live pass rate"):
            self.assertIn(token, self.text, token)

    def test_root_readme_links_it(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("IMPACT_MODEL.md", readme)


if __name__ == "__main__":
    unittest.main()
