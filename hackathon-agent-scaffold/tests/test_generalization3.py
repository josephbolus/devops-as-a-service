"""Generalization eval 3 (maximizer iteration 23).

Pins: the vendored gradebook target is genuinely distinct from ALL
THREE earlier codebases, both of its bugs are still present in
place, its baseline suite passes with both bugs present, the issue
passes the guardrail; and the committed live record
(generalization3-runs.json) and GENERALIZATION3.md agree — outcome,
tests 12 -> 18, wall clock, per-role models, both production files,
the independent probe (8/8), diff, and estimated cost — recomputed
from the record, not restated.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import run_generalization3_eval as rge  # noqa: E402
from daas import guardrail  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / "generalization3"
RECORD = ROOT / "eval-scorecard" / "generalization3-runs.json"
DOC = ROOT / "eval-scorecard" / "GENERALIZATION3.md"


class TestTargetCodebase3(unittest.TestCase):
    def test_both_bugs_still_present_in_vendored_copy(self):
        sys.path.insert(0, str(GEN))
        from gradebook.averages import weighted_mean
        from gradebook.letters import letter_grade
        self.assertEqual(weighted_mean([80, 100], [3, 1]), 170.0)
        self.assertEqual(letter_grade(90), "B")

    def test_baseline_suite_passes_with_bugs(self):
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
            cwd=GEN, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Ran 12 tests", proc.stderr)

    def test_distinct_from_all_three_other_codebases(self):
        self.assertTrue((GEN / "gradebook" / "averages.py").is_file())
        self.assertTrue((GEN / "gradebook" / "letters.py").is_file())
        for other in ("app", "ledgerlite", "textkit"):
            self.assertFalse((GEN / other).exists(), other)
        issue = json.loads((GEN / "issue.json").read_text())
        seeded = {json.loads(p.read_text())["title"]
                  for p in (ROOT / "hackathon-agent-scaffold" / "issues").glob("*.json")}
        earlier = [json.loads((ROOT / d / "issue.json").read_text())["title"]
                   for d in ("generalization", "generalization2")]
        self.assertNotIn(issue["title"], seeded)
        self.assertNotIn(issue["title"], earlier)
        blocked, _ = guardrail.check(issue["title"], issue.get("body", ""))
        self.assertFalse(blocked)

    def test_runner_uses_kept_split_and_generalization3_target(self):
        self.assertEqual(rge.SPLIT_ROLE_MODELS,
                         {"CODER": "muse-wonder-1.0",
                          "REVIEWER": "muse-wonder-1.0"})
        self.assertEqual(rge.GEN_REPO, GEN)
        self.assertEqual(rge.PRODUCTION_FILES,
                         ["gradebook/averages.py", "gradebook/letters.py"])


class TestCommittedRecord3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(RECORD.read_text())
        cls.rec = cls.doc["runs"][0]

    def test_live_run_passed_with_actual_models(self):
        self.assertEqual(self.doc["summary"]["passed"], True)
        self.assertEqual(self.rec["outcome"], "passed")
        self.assertEqual(self.rec["pipeline_outcome"], "passed")
        self.assertEqual((self.rec["tests_before"], self.rec["tests_after"]), (12, 18))
        self.assertEqual(self.doc["summary"]["test_growth"], 6)
        self.assertEqual(self.rec["wall_clock_seconds"], 42.41)
        self.assertEqual(self.rec["model_calls"], 4)
        models = self.rec["models_by_role"]
        self.assertEqual(models["CODER"], "muse-wonder-1.0")
        self.assertEqual(models["REVIEWER"], "muse-wonder-1.0")
        self.assertEqual(models["TRIAGE"], "muse-spark-1.3")
        self.assertEqual(models["PLANNER"], "muse-spark-1.3")
        self.assertEqual(self.rec["reviewer_verdict"], "approve")
        self.assertEqual(self.rec["unexpected_files"], [])
        self.assertEqual(self.rec["files_touched"],
                         ["gradebook/averages.py", "gradebook/letters.py",
                          "tests/test_gradebook_regression.py"])
        self.assertEqual(self.rec["production_files_touched"],
                         ["gradebook/averages.py", "gradebook/letters.py"])
        self.assertAlmostEqual(self.rec["cost"]["total_usd_est"], 0.024813, places=6)
        self.assertEqual(self.rec["cost"]["method"], "char_estimate")

    def test_independent_probe_all_passed(self):
        self.assertTrue(self.rec["probe_passed"])
        self.assertEqual(len(self.rec["probe"]), 8)
        self.assertTrue(all(c["passed"] for c in self.rec["probe"]))
        by_check = {c["check"]: c for c in self.rec["probe"]}
        self.assertEqual(by_check["letter_grade(90)"]["actual"], "A")
        self.assertEqual(by_check["weighted_mean([80, 100], [3, 1])"]["actual"], 85.0)
        self.assertEqual(by_check["final_letter([80, 100], [3, 1])"]["actual"], "B")

    def test_record_diff_and_doc_agree(self):
        self.assertIn("/ total_weight", self.rec["diff"])
        self.assertIn("score >= 90", self.rec["diff"])
        self.assertIn("tests/test_gradebook_regression.py", self.rec["diff"])
        self.assertIn("12 → 18 discovered", self.rec["pr_body"])
        text = DOC.read_text(encoding="utf-8")
        for token in ("12 → 18", "+6", "42.41s", "gradebook",
                      "generalization3-runs.json", "170.0",
                      "not tuned", "$0.0248", "8/8"):
            self.assertIn(token, text, token)


if __name__ == "__main__":
    unittest.main()
