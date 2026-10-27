"""Pin the frontier current-baseline live record (iteration 48).

The record (eval-scorecard/frontier-current-runs.json +
FRONTIER_CURRENT.md) must stay internally consistent: the runs are
recomputed from the rows, every role's recorded model must be
muse-wonder-1.0 with no fallbacks/retries, the embedded prior
passes must match the iteration-31/32 records on disk, the
three-pass combined summary must recompute, and the markdown must
be exactly the runner's render of the JSON.

Note: the iteration-48 run executed twice during a
foreground/background handoff (the same duplicate-execution pattern
recorded in iterations 17/23/30/31); the pass whose summary arrived
on stdout (growth +12, 136.96s, est. $0.1102) is NOT the record
pinned here. Per the repo's authoritative-artifact rule, the
written record below -- internally consistent, with a continuous
started_at chain -- is the artifact of record.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "eval-scorecard" / "frontier-current-runs.json"
MD = ROOT / "eval-scorecard" / "FRONTIER_CURRENT.md"
RUNNER = (ROOT / "hackathon-agent-scaffold"
          / "run_frontier_current_eval.py")

EXPECTED = {"tier1": ("passed", 24, 26),
            "tier2": ("passed", 24, 28),
            "tier3": ("passed", 24, 26),
            "guardrail": ("escalated", None, None)}


def _load_runner():
    spec = importlib.util.spec_from_file_location("frcur", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(RUNNER.parent))
    spec.loader.exec_module(mod)
    return mod


class TestFrontierCurrentRecord(unittest.TestCase):
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

    def test_prior_passes_match_records(self):
        priors = {p["label"]: p for p in self.doc["prior_passes"]}
        for label, name, growth in (
                ("iteration 31", "frontier-runs.json", 10),
                ("iteration 32", "frontier-replicate-runs.json", 9)):
            doc = json.loads((ROOT / "eval-scorecard" / name)
                             .read_text(encoding="utf-8"))
            self.assertEqual(priors[label]["test_growth"], growth)
            self.assertEqual(priors[label]["work_tiers_passed"],
                             doc["summary"]["work_tiers_passed"])
            self.assertEqual(priors[label]["total_usd_est"],
                             doc["summary"]["total_usd_est"])
            for r in doc["runs"]:
                self.assertEqual(priors[label]["per_tier"][r["slug"]],
                                 [r["tests_before"], r["tests_after"]])

    def test_summary_and_combined_recompute(self):
        s = self.doc["summary"]
        self.assertEqual(s["work_tiers_passed"], "3/3")
        self.assertTrue(s["guardrail_escalated"])
        self.assertEqual(s["test_growth"], 8)
        self.assertEqual(s["total_wall_clock_seconds"], 151.91)
        self.assertEqual(s["total_usd_est"], 0.10472)
        self.assertEqual(s["cost_per_passed_issue"], 0.034907)
        c = self.doc["combined"]
        self.assertEqual(c["passes"], 3)
        self.assertEqual(c["work_tiers_passed_each"],
                         ["3/3", "3/3", "3/3"])
        self.assertEqual(c["test_growth_each"], [10, 9, 8])
        self.assertEqual(c["test_growth_mean"], 9.0)
        self.assertEqual(c["test_growth_range"], [8, 10])
        self.assertTrue(c["all_passes_passed_all_work_tiers"])
        self.assertTrue(c["all_passes_guardrail_escalated"])
        self.assertEqual(c["per_tier_growth_each"]["tier2"], [6, 5, 4])
        self.assertEqual(c["per_tier_growth_each"]["tier1"], [2, 2, 2])

    def test_markdown_is_runner_render(self):
        self.assertEqual(self.md, _load_runner().render_md(self.doc))


if __name__ == "__main__":
    unittest.main()
