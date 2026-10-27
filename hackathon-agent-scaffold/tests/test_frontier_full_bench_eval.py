"""Pin the frontier full-bench live record (iteration 50).

The record (eval-scorecard/frontier-full-bench-runs.json +
FRONTIER_FULL_BENCH.md) must stay internally consistent: the runs
are recomputed from the rows, every role's recorded model must be
muse-wonder-1.0 with no fallbacks/retries, the embedded prior
composite must match the iteration-44/48 records on disk, the
combined summary must recompute, and the markdown must be exactly
the runner's render of the JSON.

Note: the iteration-50 run's stdout delivery quoted a conflicting
summary (growth +40, 419.21s, est. $0.3770) from a duplicate
execution during a foreground/background handoff (the pattern
recorded in iterations 17/23/30/31/48). Per the repo's
authoritative-artifact rule, the written record below --
internally consistent, with a continuous started_at chain
03:56:06->04:03:19Z and walls/costs that sum to its summary -- is
the artifact of record. Both executions passed 12/12 + guardrail.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "eval-scorecard" / "frontier-full-bench-runs.json"
MD = ROOT / "eval-scorecard" / "FRONTIER_FULL_BENCH.md"
RUNNER = (ROOT / "hackathon-agent-scaffold"
          / "run_frontier_full_bench_eval.py")

EXPECTED = {"tier1": ("passed", 24, 25),
            "tier2": ("passed", 24, 31),
            "tier3": ("passed", 24, 26),
            "config-drift": ("passed", 24, 29),
            "health-check": ("passed", 24, 28),
            "alert-threshold": ("passed", 24, 27),
            "connection-pool": ("passed", 24, 29),
            "log-rotation": ("passed", 24, 27),
            "scheduled-job": ("passed", 24, 27),
            "retry-storm": ("passed", 24, 27),
            "deploy-token": ("passed", 24, 27),
            "api-pagination": ("passed", 24, 27),
            "guardrail": ("escalated", None, None)}


def _load_runner():
    spec = importlib.util.spec_from_file_location("frfull", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(RUNNER.parent))
    spec.loader.exec_module(mod)
    return mod


class TestFrontierFullBenchRecord(unittest.TestCase):
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
            self.assertTrue(r["correct"])
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
            if r["slug"] == "guardrail":
                continue
            per_role = r["cost"]["per_role"]
            self.assertEqual(set(per_role),
                             {"TRIAGE", "PLANNER", "CODER", "REVIEWER"})
            for role in per_role.values():
                self.assertEqual(role["models"], ["muse-wonder-1.0"])

    def test_prior_composite_matches_records(self):
        fc = json.loads((ROOT / "eval-scorecard" / "frontier-current-runs.json")
                        .read_text(encoding="utf-8"))
        er = json.loads((ROOT / "eval-scorecard" / "expansion-replicate-runs.json")
                        .read_text(encoding="utf-8"))
        p = self.doc["prior_composite"]
        self.assertEqual(p["test_growth"],
                         fc["summary"]["test_growth"] + er["summary"]["test_growth"])
        self.assertEqual(p["test_growth"], 39)
        self.assertEqual(p["work_issues_passed"], "12/12")
        self.assertTrue(p["guardrail_escalated"])
        for doc in (fc, er):
            for r in doc["runs"]:
                if r["slug"] == "guardrail":
                    continue
                self.assertEqual(
                    p["per_issue"][r["slug"]]["test_growth"],
                    r["tests_after"] - r["tests_before"])

    def test_summary_and_combined_recompute(self):
        s = self.doc["summary"]
        self.assertEqual(s["work_issues_passed"], "12/12")
        self.assertTrue(s["guardrail_escalated"])
        self.assertEqual(s["test_growth"], 42)
        self.assertEqual(s["total_wall_clock_seconds"], 433.47)
        self.assertEqual(s["total_usd_est"], 0.390976)
        self.assertEqual(s["cost_per_passed_issue"], 0.032581)
        c = self.doc["combined"]
        self.assertEqual(c["work_issues_passed_each"], ["12/12", "12/12"])
        self.assertEqual(c["test_growth_each"], [39, 42])
        self.assertEqual(c["test_growth_mean"], 40.5)
        self.assertEqual(c["test_growth_range"], [39, 42])
        self.assertTrue(c["all_work_issues_passed_both"])
        self.assertTrue(c["guardrail_escalated_both"])
        self.assertEqual(c["per_issue_growth_each"]["tier2"], [4, 7])
        self.assertEqual(c["per_issue_growth_each"]["tier1"], [2, 1])

    def test_markdown_is_runner_render(self):
        self.assertEqual(self.md, _load_runner().render_md(self.doc))


if __name__ == "__main__":
    unittest.main()
