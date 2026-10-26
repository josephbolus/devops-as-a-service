"""Pin the frontier replicate live record (iteration 32).

The record (eval-scorecard/frontier-replicate-runs.json +
FRONTIER_REPLICATE.md) must stay internally consistent: the
replicate runs are recomputed from the rows, every role's recorded
model must be muse-wonder-1.0 with no fallback fired, the embedded
prior pass must match iteration 31's record on disk, the combined
two-pass summary must recompute, and the markdown must be exactly
the runner's render of the JSON.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "eval-scorecard" / "frontier-replicate-runs.json"
MD = ROOT / "eval-scorecard" / "FRONTIER_REPLICATE.md"
PRIOR = ROOT / "eval-scorecard" / "frontier-runs.json"
RUNNER = (ROOT / "hackathon-agent-scaffold"
          / "run_frontier_replicate_eval.py")


def _load_runner():
    spec = importlib.util.spec_from_file_location("fr", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(RUNNER.parent))
    spec.loader.exec_module(mod)
    return mod


class TestFrontierReplicateRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(RECORD.read_text(encoding="utf-8"))
        cls.md = MD.read_text(encoding="utf-8")

    def test_runs_as_recorded(self):
        runs = {r["slug"]: r for r in self.doc["runs"]}
        self.assertEqual(
            {k: (v["outcome"], v["tests_before"], v["tests_after"])
             for k, v in runs.items()},
            {"tier1": ("passed", 6, 8), "tier2": ("passed", 6, 11),
             "tier3": ("passed", 6, 8),
             "guardrail": ("escalated", None, None)})
        for r in runs.values():
            self.assertIn("muse-wonder-1.0", r["config"])
            self.assertEqual(r["fallback_stats"]["fallbacks"], 0)

    def test_every_role_used_frontier_model(self):
        for role, models in self.doc["per_role_models"].items():
            self.assertEqual(models, ["muse-wonder-1.0"], role)
        self.assertEqual(set(self.doc["per_role_models"]),
                         {"TRIAGE", "PLANNER", "CODER", "REVIEWER"})

    def test_prior_pass_matches_iteration31_record(self):
        prior_doc = json.loads(PRIOR.read_text(encoding="utf-8"))
        p = self.doc["prior_pass"]
        self.assertEqual(p["test_growth"],
                         prior_doc["summary"]["test_growth"])
        self.assertEqual(p["test_growth"], 10)
        self.assertEqual(p["total_wall_clock_seconds"], 142.52)
        self.assertEqual(p["work_tiers_passed"], "3/3")

    def test_summary_and_combined_recompute(self):
        s = self.doc["summary"]
        work = [r for r in self.doc["runs"] if r["slug"] != "guardrail"]
        passed = [r for r in work if r["outcome"] == "passed"]
        growth = sum(r["tests_after"] - r["tests_before"] for r in passed)
        self.assertEqual(s["test_growth"], growth)
        self.assertEqual(s["test_growth"], 9)
        self.assertEqual(s["work_tiers_passed"], "3/3")
        self.assertTrue(s["guardrail_escalated"])
        self.assertAlmostEqual(
            s["total_wall_clock_seconds"],
            round(sum(r["wall_clock_seconds"] for r in self.doc["runs"]), 2),
            places=1)
        self.assertEqual(s["total_wall_clock_seconds"], 171.57)
        total = round(sum((r["cost"] or {}).get("total_usd_est", 0.0)
                          for r in self.doc["runs"]), 6)
        self.assertEqual(s["total_usd_est"], total)
        self.assertEqual(s["total_usd_est"], 0.11122)
        c = self.doc["combined"]
        self.assertEqual(c["test_growth_each"], [10, 9])
        self.assertEqual(c["test_growth_mean"], 9.5)
        self.assertEqual(c["test_growth_range"], [9, 10])
        self.assertTrue(c["both_guardrail_escalated"])
        self.assertTrue(c["both_passed_all_work_tiers"])
        self.assertEqual(c["work_tiers_passed_each"], ["3/3", "3/3"])

    def test_markdown_is_runner_render(self):
        self.assertEqual(self.md, _load_runner().render_md(self.doc))


if __name__ == "__main__":
    unittest.main()
