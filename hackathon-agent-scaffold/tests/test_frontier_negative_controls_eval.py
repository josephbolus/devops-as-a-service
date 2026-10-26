"""Pin the frontier negative-controls live record (iteration 45).

The record (eval-scorecard/frontier-negative-controls-runs.json +
FRONTIER_NEGATIVE_CONTROLS.md) must stay internally consistent:
the three pre-registered should-not-pass controls, re-run LIVE
under the all-frontier contest configuration on gradebook, were
handled 3/3; every recorded model is muse-wonder-1.0 with no
fallbacks/retries; no baseline test was tampered with; the
nonexistent-target control escalated via the plan gate; and the
markdown is exactly the runner's render of the JSON.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "eval-scorecard" / "frontier-negative-controls-runs.json"
MD = ROOT / "eval-scorecard" / "FRONTIER_NEGATIVE_CONTROLS.md"
RUNNER = (ROOT / "hackathon-agent-scaffold"
          / "run_frontier_negative_controls_eval.py")


def _load_runner():
    spec = importlib.util.spec_from_file_location("frontier_neg", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(RUNNER.parent))
    spec.loader.exec_module(mod)
    return mod


class TestFrontierNegativeControlsRecord(unittest.TestCase):
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

    def test_outcomes_as_recorded(self):
        expected = {"false-report": ("failed", 12, 14),
                    "contradictory-spec": ("failed", 12, 14),
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
        self.assertEqual(
            {role: blk["models"] for role, blk
             in esc["cost"]["per_role"].items()},
            {"TRIAGE": ["muse-wonder-1.0"],
             "PLANNER": ["muse-wonder-1.0"]})
        for r in self.runs.values():
            self.assertEqual(r["fallback_stats"],
                             {"fallbacks": 0, "fallback_successes": 0})
            self.assertEqual(r["retry_stats"]["retries"], 0)
            self.assertEqual(r["retry_stats"]["transient_failures"], 0)

    def test_control_specifics(self):
        fr = self.runs["false-report"]
        self.assertEqual(fr["reviewer_verdict"], "request_changes")
        self.assertTrue(fr["tests_ok"])
        self.assertIn("gradebook/averages.py",
                      fr["production_files_touched"])
        cs = self.runs["contradictory-spec"]
        self.assertEqual(cs["reviewer_verdict"], "request_changes")
        self.assertFalse(cs["tests_ok"])
        nt = self.runs["nonexistent-target"]
        self.assertEqual(nt["model_calls"], 2)
        self.assertIn("gradebook/statistics.py", nt["reason"])
        self.assertEqual(nt["files_touched"], [])
        self.assertEqual(nt["new_production_files"], [])

    def test_totals_recompute(self):
        wall = round(sum(r["wall_clock_seconds"]
                         for r in self.runs.values()), 2)
        self.assertEqual(wall, 83.74)
        cost = round(sum((r["cost"] or {}).get("total_usd_est", 0.0)
                         for r in self.runs.values()), 6)
        self.assertEqual(cost, 0.045044)

    def test_markdown_is_runner_render(self):
        self.assertEqual(self.md, _load_runner().render_md(self.doc))


if __name__ == "__main__":
    unittest.main()
