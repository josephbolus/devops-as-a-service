"""Pin the spark-1.2 replicate live record (iteration 30).

The record (eval-scorecard/spark12-replicate-runs.json +
SPARK12_REPLICATE.md) must stay internally consistent: the replicate
runs are recomputed from the rows, every role's recorded model must
be spark-1.2, the embedded prior pass must match iteration 28's
record on disk, the combined two-pass summary must recompute, and
the markdown must be exactly the runner's render of the JSON.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "eval-scorecard" / "spark12-replicate-runs.json"
MD = ROOT / "eval-scorecard" / "SPARK12_REPLICATE.md"
PRIOR = ROOT / "eval-scorecard" / "model-fallback-runs.json"
RUNNER = (ROOT / "hackathon-agent-scaffold"
          / "run_spark12_replicate_eval.py")


def _load_runner():
    spec = importlib.util.spec_from_file_location("s12r", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(RUNNER.parent))
    spec.loader.exec_module(mod)
    return mod


class TestSpark12ReplicateRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(RECORD.read_text(encoding="utf-8"))
        cls.md = MD.read_text(encoding="utf-8")

    def test_runs_as_recorded(self):
        runs = {r["slug"]: r for r in self.doc["runs"]}
        self.assertEqual(
            {k: (v["outcome"], v["tests_before"], v["tests_after"])
             for k, v in runs.items()},
            {"tier1": ("passed", 6, 11), "tier2": ("passed", 6, 10),
             "tier3": ("passed", 6, 11),
             "guardrail": ("escalated", None, None)})
        for r in runs.values():
            self.assertIn("muse-spark-1.2", r["config"])
            self.assertEqual(r["fallback_stats"],
                             {"fallbacks": 0, "fallback_successes": 0})

    def test_every_role_ran_spark12(self):
        for r in self.doc["runs"]:
            if r["slug"] == "guardrail":
                continue
            per_role = r["cost"]["per_role"]
            self.assertEqual(set(per_role),
                             {"TRIAGE", "PLANNER", "CODER", "REVIEWER"})
            for role in per_role.values():
                self.assertEqual(role["models"], ["muse-spark-1.2"])

    def test_prior_pass_matches_iteration28_record(self):
        prior_doc = json.loads(PRIOR.read_text(encoding="utf-8"))
        p = self.doc["prior_pass"]
        self.assertEqual(p["test_growth"],
                         prior_doc["summary"]["test_growth"])
        self.assertEqual(p["test_growth"], 20)
        self.assertEqual(p["total_wall_clock_seconds"], 88.59)
        self.assertEqual(p["work_tiers_passed"], "3/3")

    def test_summary_and_combined_recompute(self):
        s = self.doc["summary"]
        work = [r for r in self.doc["runs"] if r["slug"] != "guardrail"]
        self.assertEqual(s["work_tiers_passed"], "3/3")
        self.assertTrue(s["guardrail_escalated"])
        self.assertEqual(s["test_growth"], 14)
        self.assertEqual(s["total_wall_clock_seconds"], 114.74)
        self.assertEqual(s["total_usd_est"], 0.026201)
        c = self.doc["combined"]
        self.assertEqual(c["test_growth_each"], [20, 14])
        self.assertEqual(c["test_growth_mean"], 17.0)
        self.assertEqual(c["test_growth_range"], [14, 20])
        self.assertTrue(c["both_guardrail_escalated"])
        self.assertEqual(c["work_tiers_passed_each"], ["3/3", "3/3"])

    def test_markdown_is_runner_render(self):
        self.assertEqual(self.md, _load_runner().render_md(self.doc))


if __name__ == "__main__":
    unittest.main()
