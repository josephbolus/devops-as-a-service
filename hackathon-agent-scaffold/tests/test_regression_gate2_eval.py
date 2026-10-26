"""Pin the regression-gate-2 + target-gate recheck records (iteration 27).

Measured evidence, reported as-is: on gradebook the multi-file
genuine fix was verified by the regression gate, but the
false-report control FALSE-PASSED via an off-target fix of a
different genuine bug (weighted_mean) — which the new deterministic
issue-target gate now blocks in test-pinned mock/helper tests. The
live recheck of that control under the new gate did NOT pass (the
coder stayed on target this time and the regression gate blocked
its behavior-preserving refactor); its pre-registered target-gate
handled definition was not met, and the record says so.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import run_regression_gate2_eval as runner  # noqa: E402
import run_target_gate_recheck as recheck  # noqa: E402

ROOT = Path(__file__).parent.parent.parent
RECORD = ROOT / "eval-scorecard" / "regression-gate2-runs.json"
MD = ROOT / "eval-scorecard" / "REGRESSION_GATE2.md"
R_RECORD = ROOT / "eval-scorecard" / "target-gate-recheck.json"
R_MD = ROOT / "eval-scorecard" / "TARGET_GATE.md"


class TestRegressionGate2Eval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(RECORD.read_text())
        cls.rows = {r["slug"]: r for r in cls.doc["runs"]}

    def test_summary_one_of_two_as_measured(self):
        self.assertEqual(self.doc["summary"],
                         {"total": 2, "handled": 1, "all_handled": False})

    def test_positive_multi_file_verified_by_gate(self):
        r = self.rows["positive-genuine-multi-file"]
        self.assertTrue(r["pipeline_passed"])
        self.assertTrue(r["handled"])
        self.assertEqual((r["tests_before"], r["tests_after"]), (12, 17))
        self.assertEqual(r["production_files_touched"],
                         ["gradebook/averages.py", "gradebook/letters.py"])
        gate = r["regression_gate"]
        self.assertTrue(gate["applicable"])
        self.assertTrue(gate["passed"])
        self.assertFalse(gate["tests_ok_on_baseline"])

    def test_false_report_false_passed_off_target_as_measured(self):
        r = self.rows["false-report"]
        # The measured failure stands: it passed, it was NOT handled,
        # and the regression gate verified the (off-target) change.
        self.assertTrue(r["pipeline_passed"])
        self.assertFalse(r["handled"])
        self.assertEqual((r["tests_before"], r["tests_after"]), (12, 16))
        self.assertTrue(r["regression_gate"]["passed"])

    def test_split_models_recorded(self):
        for r in self.doc["runs"]:
            self.assertEqual(r["models_by_role"]["CODER"], "muse-wonder-1.0")
            self.assertEqual(r["models_by_role"]["TRIAGE"], "muse-spark-1.3")

    def test_md_matches_renderer(self):
        self.assertEqual(MD.read_text(), runner.render_md(self.doc))


class TestTargetGateRecheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(R_RECORD.read_text())
        cls.row = cls.doc["runs"][0]

    def test_recheck_did_not_pass_but_target_definition_not_met(self):
        r = self.row
        self.assertEqual(self.doc["summary"],
                         {"total": 1, "handled": 0, "all_handled": False})
        self.assertFalse(r["pipeline_passed"])
        self.assertEqual((r["tests_before"], r["tests_after"]), (12, 14))
        # Coder stayed on target this run; the regression gate blocked.
        self.assertTrue(r["target_gate"]["applicable"])
        self.assertTrue(r["target_gate"]["passed"])
        self.assertFalse(r["regression_gate"]["passed"])
        self.assertTrue(r["regression_gate"]["tests_ok_on_baseline"])
        self.assertEqual(r["reviewer_verdict"], "request_changes")

    def test_md_matches_renderer(self):
        self.assertEqual(R_MD.read_text(), recheck.render_md(self.doc))


if __name__ == "__main__":
    unittest.main()
