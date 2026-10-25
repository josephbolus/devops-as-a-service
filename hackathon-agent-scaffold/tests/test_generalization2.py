"""Generalization eval 2 (maximizer iteration 19).

Pins: the vendored textkit target is genuinely distinct from BOTH the
seeded demo repo and ledgerlite, its bug is still present in place,
its baseline suite passes with the bug present, the issue passes the
guardrail; and the committed live record (generalization2-runs.json)
and GENERALIZATION2.md agree — outcome, tests 10 -> 15, wall clock,
per-role models, files, diff, and estimated cost — recomputed from
the record, not restated.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import run_generalization2_eval as rge  # noqa: E402
from daas import guardrail  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / "generalization2"
RECORD = ROOT / "eval-scorecard" / "generalization2-runs.json"
DOC = ROOT / "eval-scorecard" / "GENERALIZATION2.md"


class TestTargetCodebase2(unittest.TestCase):
    def test_bug_still_present_in_vendored_copy(self):
        sys.path.insert(0, str(GEN))
        from textkit.tokens import first_words
        self.assertEqual(first_words("alpha beta gamma delta", 2),
                         "alpha beta gamma")

    def test_baseline_suite_passes_with_bug(self):
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
            cwd=GEN, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Ran 10 tests", proc.stderr)

    def test_distinct_from_both_other_codebases(self):
        self.assertTrue((GEN / "textkit" / "tokens.py").is_file())
        self.assertFalse((GEN / "app").exists())
        self.assertFalse((GEN / "ledgerlite").exists())
        issue = json.loads((GEN / "issue.json").read_text())
        seeded = {json.loads(p.read_text())["title"]
                  for p in (ROOT / "hackathon-agent-scaffold" / "issues").glob("*.json")}
        gen1 = json.loads((ROOT / "generalization" / "issue.json").read_text())
        self.assertNotIn(issue["title"], seeded)
        self.assertNotEqual(issue["title"], gen1["title"])
        blocked, _ = guardrail.check(issue["title"], issue.get("body", ""))
        self.assertFalse(blocked)

    def test_runner_uses_kept_split_and_generalization2_target(self):
        self.assertEqual(rge.SPLIT_ROLE_MODELS,
                         {"CODER": "muse-wonder-1.0",
                          "REVIEWER": "muse-wonder-1.0"})
        self.assertEqual(rge.GEN_REPO, GEN)


class TestCommittedRecord2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(RECORD.read_text())
        cls.rec = cls.doc["runs"][0]

    def test_live_run_passed_with_actual_models(self):
        self.assertEqual(self.doc["summary"]["passed"], True)
        self.assertEqual(self.rec["outcome"], "passed")
        self.assertEqual((self.rec["tests_before"], self.rec["tests_after"]), (10, 15))
        self.assertEqual(self.doc["summary"]["test_growth"], 5)
        self.assertEqual(self.rec["wall_clock_seconds"], 31.98)
        self.assertEqual(self.rec["model_calls"], 4)
        models = self.rec["models_by_role"]
        self.assertEqual(models["CODER"], "muse-wonder-1.0")
        self.assertEqual(models["REVIEWER"], "muse-wonder-1.0")
        self.assertEqual(models["TRIAGE"], "muse-spark-1.3")
        self.assertEqual(models["PLANNER"], "muse-spark-1.3")
        self.assertEqual(self.rec["reviewer_verdict"], "approve")
        self.assertEqual(self.rec["unexpected_files"], [])
        self.assertEqual(self.rec["files_touched"],
                         ["tests/test_tokens_regression.py", "textkit/tokens.py"])
        self.assertAlmostEqual(self.rec["cost"]["total_usd_est"], 0.014396, places=6)
        self.assertEqual(self.rec["cost"]["method"], "char_estimate")

    def test_record_diff_and_doc_agree(self):
        self.assertIn('words[:n]', self.rec["diff"])
        self.assertIn("tests/test_tokens_regression.py", self.rec["diff"])
        self.assertIn("10 → 15 discovered", self.rec["pr_body"])
        text = DOC.read_text(encoding="utf-8")
        for token in ("10 → 15", "+5", "31.98s", "textkit",
                      "generalization2-runs.json", "alpha beta gamma",
                      "not tuned", "$0.0144"):
            self.assertIn(token, text, token)


if __name__ == "__main__":
    unittest.main()
