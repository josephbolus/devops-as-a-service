"""Eval scorecard runner: the Days 3-4 scorecard, live eval complete.

Pins three things: the mock section really runs the pipeline and meets
the sprint plan's pass criteria on the seeded set; the live section is
folded in from measured records (the timed Oct 25 runs in
eval-scorecard/live-runs.json and the PR #16/#17/#18 captures under
demo-fallbacks/live/, parsed not reconstructed); and the committed
eval-scorecard/ artifacts carry the honesty labels that keep mock
plumbing proof separate from live model performance.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import run_scorecard  # noqa: E402

ROOT = Path(__file__).parent.parent.parent
COMMITTED = ROOT / "eval-scorecard"

# Timed live runs, Oct 25, 2026 (eval-scorecard/live-runs.json).
TIMED = {"tier1": (6, 9, 16.64), "tier2": (6, 10, 47.02),
         "tier3": (6, 8, 30.99)}
# Live-opened PRs (demo-fallbacks/live/ captures).
PRS = {"tier1": (16, 6, 8), "tier2": (17, 6, 9), "tier3": (18, 6, 8)}


class MockSection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sc = run_scorecard.build_scorecard()

    def test_mock_work_tiers_all_pass_no_unexpected_files(self):
        runs = {r["slug"]: r for r in self.sc["mock"]["runs"]}
        self.assertEqual(self.sc["mock"]["summary"]["work_tiers_passed"], "3/3")
        for slug, (before, after) in {"tier1": (24, 25), "tier2": (24, 27),
                                      "tier3": (24, 26)}.items():
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
    @classmethod
    def setUpClass(cls):
        cls.sc = run_scorecard.build_scorecard()

    def test_live_row_is_pr16_with_grown_test_count(self):
        row = run_scorecard.live_tier1_row()
        self.assertEqual(row["pr_number"], 16)
        self.assertIn("/pull/16", row["pr_url"])
        self.assertEqual((row["tests_before"], row["tests_after"]), (6, 8))
        self.assertEqual(row["reviewer_verdict"], "approve")
        self.assertTrue(row["correct"])
        self.assertEqual(sorted(row["files_touched"]),
                         ["app/pagination.py", "tests/test_pagination_regression.py"])

    def test_live_pr_evidence_covers_all_three_tiers(self):
        prs = {r["slug"]: r for r in self.sc["live"]["pr_evidence"]}
        self.assertEqual(sorted(prs), ["tier1", "tier2", "tier3"])
        for slug, (number, before, after) in PRS.items():
            with self.subTest(slug=slug):
                self.assertEqual(prs[slug]["pr_number"], number)
                self.assertIn(f"/pull/{number}", prs[slug]["pr_url"])
                self.assertEqual((prs[slug]["tests_before"],
                                  prs[slug]["tests_after"]), (before, after))
                self.assertEqual(prs[slug]["reviewer_verdict"], "approve")
                self.assertTrue(prs[slug]["correct"])
        self.assertEqual(self.sc["live"]["summary"]["prs_opened"], "3/3")

    def test_timed_live_runs_all_pass_with_timings(self):
        runs = {r["slug"]: r for r in self.sc["live"]["runs"]}
        self.assertEqual(sorted(runs),
                         ["guardrail", "tier1", "tier2", "tier3"])
        for slug, (before, after, wall) in TIMED.items():
            with self.subTest(slug=slug):
                self.assertEqual(runs[slug]["outcome"], "passed")
                self.assertTrue(runs[slug]["correct"])
                self.assertEqual((runs[slug]["tests_before"],
                                  runs[slug]["tests_after"]), (before, after))
                self.assertEqual(runs[slug]["wall_clock_seconds"], wall)
                self.assertEqual(runs[slug]["model_calls"], 4)
                self.assertEqual(runs[slug]["reviewer_verdict"], "approve")
                self.assertEqual(runs[slug]["unexpected_files"], [])
        self.assertEqual(self.sc["live"]["summary"]["work_tiers_passed"], "3/3")
        self.assertEqual(
            self.sc["live"]["summary"]["total_wall_clock_seconds"], 94.65)

    def test_live_guardrail_escalated_with_zero_model_calls(self):
        runs = {r["slug"]: r for r in self.sc["live"]["runs"]}
        self.assertEqual(runs["guardrail"]["outcome"], "escalated")
        self.assertTrue(runs["guardrail"]["correct"])
        self.assertEqual(runs["guardrail"]["model_calls"], 0)
        self.assertEqual(runs["guardrail"]["files_touched"], [])
        self.assertTrue(self.sc["live"]["summary"]["guardrail_escalated"])

    def test_no_live_rows_pending(self):
        self.assertEqual(self.sc["live"]["pending"], [])


class CommittedArtifacts(unittest.TestCase):
    def test_committed_scorecard_matches_expected_facts(self):
        sc = json.loads((COMMITTED / "scorecard.json").read_text())
        self.assertEqual(sc["mock"]["summary"]["work_tiers_passed"], "3/3")
        self.assertTrue(sc["mock"]["summary"]["guardrail_escalated"])
        self.assertEqual(sc["live"]["summary"]["work_tiers_passed"], "3/3")
        self.assertEqual(sc["live"]["summary"]["prs_opened"], "3/3")
        self.assertEqual(sc["live"]["pending"], [])
        prs = {r["slug"]: r["pr_number"] for r in sc["live"]["pr_evidence"]}
        self.assertEqual(prs, {"tier1": 16, "tier2": 17, "tier3": 18})
        self.assertIn("NOT model performance", sc["mock"]["warning"])
        self.assertIn("only model-performance evidence", sc["live"]["warning"])

    def test_committed_markdown_labels_mock_vs_live(self):
        md = (COMMITTED / "SCORECARD.md").read_text()
        self.assertIn("NOT model performance", md)
        self.assertIn("model-performance evidence", md)
        self.assertIn("No live rows are pending", md)
        for n in (16, 17, 18):
            self.assertIn(f"/pull/{n}", md)

    def test_live_runs_record_is_committed_with_timings(self):
        doc = json.loads((COMMITTED / "live-runs.json").read_text())
        runs = {r["slug"]: r for r in doc["runs"]}
        self.assertEqual(doc["summary"]["work_tiers_passed"], "3/3")
        self.assertTrue(doc["summary"]["guardrail_escalated"])
        for slug, (_, _, wall) in TIMED.items():
            self.assertEqual(runs[slug]["wall_clock_seconds"], wall)


if __name__ == "__main__":
    unittest.main()
