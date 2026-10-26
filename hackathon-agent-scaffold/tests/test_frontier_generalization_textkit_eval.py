"""Pin the frontier generalization (textkit) live record (iteration 39).

The record (eval-scorecard/frontier-generalization-textkit-runs.json
+ FRONTIER_GENERALIZATION_TEXTKIT.md) must stay internally
consistent: the all-frontier run on the unseen textkit codebase is
recomputed from the row, every role's recorded model must be
muse-wonder-1.0 with no fallback fired, the independent probe must be
7/7, the embedded prior pass must match iteration 19's split record on
disk, the vendored target must still carry the bug, and the markdown
must be exactly the runner's render of the JSON.
"""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = (ROOT / "eval-scorecard"
          / "frontier-generalization-textkit-runs.json")
MD = ROOT / "eval-scorecard" / "FRONTIER_GENERALIZATION_TEXTKIT.md"
PRIOR = ROOT / "eval-scorecard" / "generalization2-runs.json"
GEN = ROOT / "generalization2"
RUNNER = (ROOT / "hackathon-agent-scaffold"
          / "run_frontier_generalization_textkit_eval.py")


def _load_runner():
    spec = importlib.util.spec_from_file_location("fgt", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(RUNNER.parent))
    spec.loader.exec_module(mod)
    return mod


class TestFrontierGeneralizationTextkitRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(RECORD.read_text(encoding="utf-8"))
        cls.md = MD.read_text(encoding="utf-8")
        cls.rec = cls.doc["runs"][0]

    def test_run_as_recorded(self):
        r = self.rec
        self.assertEqual(r["outcome"], "passed")
        self.assertEqual(r["pipeline_outcome"], "passed")
        self.assertEqual((r["tests_before"], r["tests_after"]), (10, 11))
        self.assertEqual(r["wall_clock_seconds"], 18.14)
        self.assertEqual(r["model_calls"], 4)
        self.assertEqual(r["reviewer_verdict"], "approve")
        self.assertTrue(r["tests_ok"])
        self.assertEqual(r["unexpected_files"], [])
        self.assertEqual(r["production_files_touched"],
                         ["textkit/tokens.py"])
        self.assertEqual(r["files_touched"],
                         ["tests/test_tokens_regression.py",
                          "textkit/tokens.py"])
        self.assertIn("words[:n]", r["diff"])

    def test_every_role_used_frontier_model_no_fallback(self):
        self.assertEqual(self.rec["models_by_role"],
                         {"TRIAGE": "muse-wonder-1.0",
                          "PLANNER": "muse-wonder-1.0",
                          "CODER": "muse-wonder-1.0",
                          "REVIEWER": "muse-wonder-1.0"})
        for role, blk in self.rec["cost"]["per_role"].items():
            self.assertEqual(blk["models"], ["muse-wonder-1.0"], role)
        self.assertEqual(self.rec["fallback_stats"],
                         {"fallbacks": 0, "fallback_successes": 0})
        self.assertEqual(self.rec["retry_stats"]["retries"], 0)
        self.assertIn("muse-wonder-1.0", self.rec["config"])
        self.assertIn("fallback", self.rec["config"])

    def test_independent_probe_all_passed(self):
        self.assertTrue(self.rec["probe_passed"])
        self.assertEqual(len(self.rec["probe"]), 7)
        self.assertTrue(all(c["passed"] for c in self.rec["probe"]))
        by_check = {c["check"]: c for c in self.rec["probe"]}
        self.assertEqual(
            by_check["first_words('alpha beta gamma delta', 2)"]["actual"],
            "alpha beta")
        self.assertEqual(
            by_check["first_words('alpha beta gamma delta', 0)"]["actual"],
            "")

    def test_summary_recomputes_and_prior_matches_iteration19(self):
        s = self.doc["summary"]
        self.assertTrue(s["passed"])
        self.assertEqual(s["test_growth"], 1)
        self.assertEqual(s["wall_clock_seconds"], 18.14)
        self.assertEqual(s["total_usd_est"], 0.016772)
        self.assertAlmostEqual(
            s["total_usd_est"], self.rec["cost"]["total_usd_est"],
            places=6)
        prior_doc = json.loads(PRIOR.read_text(encoding="utf-8"))
        p = self.doc["prior_split_pass"]
        self.assertEqual(p["test_growth"],
                         prior_doc["summary"]["test_growth"])
        self.assertEqual(p["wall_clock_seconds"], 31.98)
        self.assertEqual(p["outcome"], "passed")
        self.assertEqual(p["models_by_role"]["TRIAGE"],
                         "muse-spark-1.3")
        self.assertEqual(p["total_usd_est"], 0.014396)

    def test_vendored_target_still_carries_the_bug(self):
        sys.path.insert(0, str(GEN))
        from textkit.tokens import first_words
        self.assertEqual(first_words("alpha beta gamma delta", 2),
                         "alpha beta gamma")
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover",
             "-s", "tests", "-q"],
            cwd=GEN, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Ran 10 tests", proc.stderr)

    def test_markdown_is_runner_render(self):
        self.assertEqual(self.md, _load_runner().render_md(self.doc))


if __name__ == "__main__":
    unittest.main()
