"""Pin the expansion replicate live record (iteration 44).

The record (eval-scorecard/expansion-replicate-runs.json +
EXPANSION_REPLICATE.md) must stay internally consistent: the
replicate runs are recomputed from the rows, every role's recorded
model must be muse-wonder-1.0 with no fallbacks/retries, the
embedded prior pass must match the three batch records on disk,
the combined two-pass summary must recompute, and the markdown
must be exactly the runner's render of the JSON.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "eval-scorecard" / "expansion-replicate-runs.json"
MD = ROOT / "eval-scorecard" / "EXPANSION_REPLICATE.md"
RUNNER = (ROOT / "hackathon-agent-scaffold"
          / "run_expansion_replicate_eval.py")

EXPECTED = {"config-drift": ("passed", 24, 29),
            "health-check": ("passed", 24, 28),
            "alert-threshold": ("passed", 24, 27),
            "connection-pool": ("passed", 24, 28),
            "log-rotation": ("passed", 24, 27),
            "scheduled-job": ("passed", 24, 27),
            "retry-storm": ("passed", 24, 27),
            "deploy-token": ("passed", 24, 27),
            "api-pagination": ("passed", 24, 27)}


def _load_runner():
    spec = importlib.util.spec_from_file_location("exrep", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(RUNNER.parent))
    spec.loader.exec_module(mod)
    return mod


class TestExpansionReplicateRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(RECORD.read_text(encoding="utf-8"))
        cls.md = MD.read_text(encoding="utf-8")

    def test_runs_as_recorded(self):
        runs = {r["slug"]: r for r in self.doc["runs"]}
        self.assertEqual(
            {k: (v["outcome"], v["tests_before"], v["tests_after"])
             for k, v in runs.items()}, EXPECTED)
        for r in runs.values():
            self.assertIn("muse-wonder-1.0", r["config"])
            self.assertEqual(r["fallback_stats"],
                             {"fallbacks": 0, "fallback_successes": 0})
            self.assertEqual(r["retry_stats"]["retries"], 0)
            self.assertEqual(r["retry_stats"]["transient_failures"], 0)

    def test_every_role_ran_wonder(self):
        self.assertEqual(self.doc["per_role_models"],
                         {role: ["muse-wonder-1.0"] for role in
                          ("CODER", "PLANNER", "REVIEWER", "TRIAGE")})
        for r in self.doc["runs"]:
            per_role = r["cost"]["per_role"]
            self.assertEqual(set(per_role),
                             {"TRIAGE", "PLANNER", "CODER", "REVIEWER"})
            for role in per_role.values():
                self.assertEqual(role["models"], ["muse-wonder-1.0"])

    def test_prior_pass_matches_batch_records(self):
        total_growth = 0
        for name in ("expansion-batch1-runs.json",
                     "expansion-batch2-runs.json",
                     "expansion-batch3-runs.json"):
            doc = json.loads((ROOT / "eval-scorecard" / name)
                             .read_text(encoding="utf-8"))
            total_growth += doc["summary"]["test_growth"]
            for r in doc["runs"]:
                prior = self.doc["prior_pass"]["per_issue"][r["slug"]]
                self.assertEqual(prior["tests_before"], r["tests_before"])
                self.assertEqual(prior["tests_after"], r["tests_after"])
        self.assertEqual(self.doc["prior_pass"]["test_growth"], 32)
        self.assertEqual(total_growth, 32)
        self.assertEqual(self.doc["prior_pass"]["issues_passed"], "9/9")

    def test_summary_and_combined_recompute(self):
        s = self.doc["summary"]
        self.assertEqual(s["issues_passed"], "9/9")
        self.assertEqual(s["test_growth"], 31)
        self.assertEqual(s["total_wall_clock_seconds"], 201.76)
        self.assertEqual(s["total_usd_est"], 0.272632)
        self.assertEqual(s["cost_per_passed_issue"], 0.030292)
        c = self.doc["combined"]
        self.assertEqual(c["issues_passed_each"], ["9/9", "9/9"])
        self.assertEqual(c["test_growth_each"], [32, 31])
        self.assertEqual(c["test_growth_mean"], 31.5)
        self.assertEqual(c["test_growth_range"], [31, 32])
        self.assertTrue(c["all_issues_passed_both_passes"])
        self.assertEqual(c["per_issue_growth_each"]["deploy-token"],
                         [4, 3])
        self.assertEqual(c["per_issue_growth_each"]["config-drift"],
                         [5, 5])

    def test_markdown_is_runner_render(self):
        self.assertEqual(self.md, _load_runner().render_md(self.doc))


if __name__ == "__main__":
    unittest.main()
