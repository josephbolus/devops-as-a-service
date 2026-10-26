"""Pin the regression-gate live eval record (iteration 26).

The record in eval-scorecard/regression-gate-runs.json is the measured
evidence: a genuine textkit bug passed with the gate verified, and
the false-report control was blocked deterministically by the gate.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import run_regression_gate_eval as runner  # noqa: E402

ROOT = Path(__file__).parent.parent.parent
RECORD = ROOT / "eval-scorecard" / "regression-gate-runs.json"
MD = ROOT / "eval-scorecard" / "REGRESSION_GATE.md"


class TestRegressionGateEval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(RECORD.read_text())
        cls.rows = {r["slug"]: r for r in cls.doc["runs"]}

    def test_summary_two_of_two(self):
        self.assertEqual(self.doc["summary"],
                         {"total": 2, "handled": 2, "all_handled": True})

    def test_positive_verified_by_gate(self):
        r = self.rows["positive-genuine-bug"]
        self.assertTrue(r["pipeline_passed"])
        self.assertEqual((r["tests_before"], r["tests_after"]), (10, 14))
        gate = r["regression_gate"]
        self.assertTrue(gate["applicable"])
        self.assertTrue(gate["passed"])
        self.assertFalse(gate["tests_ok_on_baseline"])

    def test_false_report_blocked_by_gate(self):
        r = self.rows["false-report"]
        self.assertFalse(r["pipeline_passed"])
        gate = r["regression_gate"]
        self.assertTrue(gate["applicable"])
        self.assertFalse(gate["passed"])
        self.assertTrue(gate["tests_ok_on_baseline"])

    def test_split_models_recorded(self):
        for r in self.doc["runs"]:
            self.assertEqual(r["models_by_role"]["CODER"], "muse-wonder-1.0")
            self.assertEqual(r["models_by_role"]["TRIAGE"], "muse-spark-1.3")

    def test_md_matches_renderer(self):
        self.assertEqual(MD.read_text(), runner.render_md(self.doc))


if __name__ == "__main__":
    unittest.main()
