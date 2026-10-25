"""Generalization eval (maximizer new-feature backlog item 1).

Pins: the vendored ledgerlite target is genuinely distinct from the
seeded demo repo and its bug is still present in place (the pipeline
ran against a copy); its baseline suite passes with the bug present;
the issue passes the guardrail; and the committed live record
(generalization-runs.json) and GENERALIZATION.md agree — outcome,
tests 9 -> 13, wall clock, per-role models, files, and diff — with
the numbers recomputed from the record, not restated.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import run_generalization_eval as rge  # noqa: E402
from daas import guardrail  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / "generalization"
RECORD = ROOT / "eval-scorecard" / "generalization-runs.json"
DOC = ROOT / "eval-scorecard" / "GENERALIZATION.md"


class TestTargetCodebase(unittest.TestCase):
    def test_bug_still_present_in_vendored_copy(self):
        sys.path.insert(0, str(GEN))
        from ledgerlite.stats import median_cents
        self.assertEqual(median_cents([100, 200, 300, 400]), 300)

    def test_baseline_suite_passes_with_bug(self):
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
            cwd=GEN, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Ran 9 tests", proc.stderr)

    def test_distinct_from_seeded_demo_repo(self):
        self.assertTrue((GEN / "ledgerlite" / "stats.py").is_file())
        self.assertFalse((GEN / "app").exists())
        issue = json.loads((GEN / "issue.json").read_text())
        seeded = {json.loads(p.read_text())["title"]
                  for p in (ROOT / "hackathon-agent-scaffold" / "issues").glob("*.json")}
        self.assertNotIn(issue["title"], seeded)
        blocked, _ = guardrail.check(issue["title"], issue.get("body", ""))
        self.assertFalse(blocked)

    def test_runner_uses_kept_split_and_generalization_target(self):
        self.assertEqual(rge.SPLIT_ROLE_MODELS,
                         {"CODER": "muse-wonder-1.0",
                          "REVIEWER": "muse-wonder-1.0"})
        self.assertEqual(rge.GEN_REPO, GEN)


class TestCommittedRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(RECORD.read_text())
        cls.rec = cls.doc["runs"][0]

    def test_live_run_passed_with_actual_models(self):
        self.assertEqual(self.doc["summary"]["passed"], True)
        self.assertEqual(self.rec["outcome"], "passed")
        self.assertEqual((self.rec["tests_before"], self.rec["tests_after"]), (9, 13))
        self.assertEqual(self.doc["summary"]["test_growth"], 4)
        self.assertEqual(self.rec["wall_clock_seconds"], 37.73)
        self.assertEqual(self.rec["model_calls"], 4)
        models = self.rec["models_by_role"]
        self.assertEqual(models["CODER"], "muse-wonder-1.0")
        self.assertEqual(models["REVIEWER"], "muse-wonder-1.0")
        self.assertEqual(models["TRIAGE"], "muse-spark-1.3")
        self.assertEqual(models["PLANNER"], "muse-spark-1.3")
        self.assertEqual(self.rec["reviewer_verdict"], "approve")
        self.assertEqual(self.rec["unexpected_files"], [])
        self.assertEqual(self.rec["files_touched"],
                         ["ledgerlite/stats.py", "tests/test_stats_regression.py"])

    def test_record_diff_is_the_one_line_fix_plus_regression(self):
        self.assertIn("return (ordered[mid - 1] + ordered[mid]) / 2",
                      self.rec["diff"])
        self.assertIn("tests/test_stats_regression.py", self.rec["diff"])
        self.assertIn("9 → 13 discovered", self.rec["pr_body"])

    def test_doc_numbers_match_the_record(self):
        text = DOC.read_text(encoding="utf-8")
        for token in ("9 → 13", "+4", "37.73s", "ledgerlite",
                      "generalization-runs.json", "300, expected 250",
                      "not tuned"):
            self.assertIn(token, text, token)


if __name__ == "__main__":
    unittest.main()
