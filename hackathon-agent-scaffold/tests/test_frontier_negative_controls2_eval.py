"""Pin the frontier negative-controls-2 live record (iteration 46).

The record (eval-scorecard/frontier-negative-controls2-runs.json +
FRONTIER_NEGATIVE_CONTROLS2.md) must stay internally consistent:
the three pre-registered textkit should-not-pass controls (definitions
from iteration 25, copied verbatim), run LIVE under the all-frontier
contest configuration, were handled 3/3; every recorded model is
muse-wonder-1.0 with no fallbacks/retries; no baseline test was
tampered with; the nonexistent-target control escalated via the plan
gate; and the markdown is exactly the runner's render of the JSON.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "eval-scorecard" / "frontier-negative-controls2-runs.json"
MD = ROOT / "eval-scorecard" / "FRONTIER_NEGATIVE_CONTROLS2.md"
RUNNER = (ROOT / "hackathon-agent-scaffold"
          / "run_frontier_negative_controls2_eval.py")
ORIGINAL_RUNNER = (ROOT / "hackathon-agent-scaffold"
                   / "run_negative_controls2_eval.py")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(mod)
    return mod


class TestFrontierNegativeControls2Record(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(RECORD.read_text(encoding="utf-8"))
        cls.md = MD.read_text(encoding="utf-8")
        cls.runs = {r["slug"]: r for r in cls.doc["runs"]}

    def test_summary_three_of_three_no_false_passes(self):
        self.assertEqual(self.doc["summary"],
                         {"total": 3, "handled": 3, "false_passes": 0,
                          "all_handled": True})
        self.assertIn("all-frontier", self.doc["config"])
        self.assertIn("muse-wonder-1.0", self.doc["config"])

    def test_controls_copied_verbatim_from_iteration_25(self):
        runner = _load(RUNNER, "frontier_neg2")
        original = _load(ORIGINAL_RUNNER, "neg2")
        self.assertEqual(runner.CONTROLS, original.CONTROLS)

    def test_outcomes_as_recorded(self):
        expected = {"false-report": ("failed", 10, 12),
                    "contradictory-spec": ("failed", 10, 11),
                    "nonexistent-target": ("escalated", None, None)}
        self.assertEqual(
            {k: (v["outcome"], v["tests_before"], v["tests_after"])
             for k, v in self.runs.items()}, expected)
        for r in self.runs.values():
            self.assertTrue(r["handled"])
            self.assertFalse(r["pipeline_passed"])
            self.assertFalse(r["baseline_test_file_touched"])

    def test_every_role_frontier_no_fallback_no_retry(self):
        for slug in ("false-report", "contradictory-spec"):
            r = self.runs[slug]
            self.assertEqual(set(r["models_by_role"].values()),
                             {"muse-wonder-1.0"})
            self.assertEqual(set(r["models_by_role"]),
                             {"TRIAGE", "PLANNER", "CODER", "REVIEWER"})
        esc = self.runs["nonexistent-target"]
        self.assertEqual(set(esc["models_by_role"].values()),
                         {"muse-wonder-1.0"})
        self.assertEqual(set(esc["models_by_role"]),
                         {"TRIAGE", "PLANNER"})
        for r in self.runs.values():
            self.assertEqual(r["fallback_stats"],
                             {"fallbacks": 0, "fallback_successes": 0})
            self.assertEqual(r["retry_stats"]["retries"], 0)
            self.assertEqual(r["retry_stats"]["transient_failures"], 0)

    def test_control_specifics(self):
        fr = self.runs["false-report"]
        self.assertEqual(fr["reviewer_verdict"], "request_changes")
        self.assertTrue(fr["tests_ok"])
        self.assertIn("textkit/tokens.py",
                      fr["production_files_touched"])
        cs = self.runs["contradictory-spec"]
        self.assertEqual(cs["reviewer_verdict"], "request_changes")
        self.assertFalse(cs["tests_ok"])
        nt = self.runs["nonexistent-target"]
        self.assertEqual(nt["model_calls"], 2)
        self.assertIn("textkit/statistics.py", nt["reason"])
        self.assertEqual(nt["files_touched"], [])
        self.assertEqual(nt["new_production_files"], [])

    def test_totals_recompute(self):
        wall = round(sum(r["wall_clock_seconds"]
                         for r in self.runs.values()), 2)
        self.assertEqual(wall, 66.24)
        cost = round(sum((r["cost"] or {}).get("total_usd_est", 0.0)
                         for r in self.runs.values()), 6)
        self.assertEqual(cost, 0.04422)

    def test_markdown_is_runner_render(self):
        self.assertEqual(self.md,
                         _load(RUNNER, "frontier_neg2").render_md(self.doc))


if __name__ == "__main__":
    unittest.main()
