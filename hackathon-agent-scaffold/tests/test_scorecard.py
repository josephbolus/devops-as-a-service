"""Eval scorecard runner: the Days 3-4 scorecard, published early.

Pins three things: the mock section really runs the pipeline and meets
the sprint plan's pass criteria on the seeded set; the live section is
parsed from the captured PR #16 artifacts (not reconstructed); and the
committed eval-scorecard/ artifacts carry the honesty labels that keep
mock plumbing proof separate from live model performance.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import run_scorecard  # noqa: E402

ROOT = Path(__file__).parent.parent.parent
COMMITTED = ROOT / "eval-scorecard"


class MockSection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sc = run_scorecard.build_scorecard()

    def test_mock_work_tiers_all_pass_no_unexpected_files(self):
        runs = {r["slug"]: r for r in self.sc["mock"]["runs"]}
        self.assertEqual(self.sc["mock"]["summary"]["work_tiers_passed"], "3/3")
        for slug, (before, after) in {"tier1": (6, 7), "tier2": (6, 9),
                                      "tier3": (6, 8)}.items():
            with self.subTest(slug=slug):
                self.assertEqual(runs[slug]["outcome"], "passed")
                self.assertEqual((runs[slug]["tests_before"],
                                  runs[slug]["tests_after"]), (before, after))
                self.assertEqual(runs[slug]["unexpected_files"], [])
                self.assertTrue(runs[slug]["pr_produced"])

    def test_mock_guardrail_escalates_and_touches_nothing(self):
        runs = {r["slug"]: r for r in self.sc["mock"]["runs"]}
        self.assertTrue(self.sc["mock"]["summary"]["guardrail_escalated"])
        self.assertEqual(runs["guardrail"]["outcome"], "escalated")
        self.assertEqual(runs["guardrail"]["files_touched"], [])
        self.assertFalse(runs["guardrail"]["pr_produced"])


class LiveSection(unittest.TestCase):
    def test_live_row_is_pr16_with_grown_test_count(self):
        row = run_scorecard.live_tier1_row()
        self.assertEqual(row["pr_number"], 16)
        self.assertIn("/pull/16", row["pr_url"])
        self.assertEqual((row["tests_before"], row["tests_after"]), (6, 8))
        self.assertEqual(row["reviewer_verdict"], "approve")
        self.assertTrue(row["correct"])
        self.assertEqual(sorted(row["files_touched"]),
                         ["app/pagination.py", "tests/test_pagination_regression.py"])

    def test_live_pending_tiers_are_named_not_faked(self):
        sc = run_scorecard.build_scorecard()
        pending = " ".join(sc["live"]["pending"])
        for slug in ("tier2", "tier3", "guardrail"):
            self.assertIn(slug, pending)
        self.assertEqual(len(sc["live"]["runs"]), 1)


class CommittedArtifacts(unittest.TestCase):
    def test_committed_scorecard_matches_expected_facts(self):
        sc = json.loads((COMMITTED / "scorecard.json").read_text())
        self.assertEqual(sc["mock"]["summary"]["work_tiers_passed"], "3/3")
        self.assertTrue(sc["mock"]["summary"]["guardrail_escalated"])
        self.assertEqual(sc["live"]["runs"][0]["pr_number"], 16)
        self.assertIn("NOT model performance", sc["mock"]["warning"])
        self.assertIn("only model-performance evidence", sc["live"]["warning"])

    def test_committed_markdown_labels_mock_vs_live(self):
        md = (COMMITTED / "SCORECARD.md").read_text()
        self.assertIn("NOT model performance", md)
        self.assertIn("model-performance evidence", md)
        self.assertIn("Still pending", md)
        self.assertIn("/pull/16", md)


if __name__ == "__main__":
    unittest.main()
