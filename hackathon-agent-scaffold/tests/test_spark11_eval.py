"""Pin the spark-1.1 live pipeline record (iteration 29).

The record (eval-scorecard/spark11-runs.json + SPARK11.md) must stay
internally consistent: the seeded-set runs on muse-spark-1.1 are
recomputed from the rows, every role's recorded model must be
spark-1.1, and the markdown must be exactly the runner's render of
the JSON — a stale or hand-edited summary fails here.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "eval-scorecard" / "spark11-runs.json"
MD = ROOT / "eval-scorecard" / "SPARK11.md"
RUNNER = ROOT / "hackathon-agent-scaffold" / "run_spark11_eval.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("s11", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(RUNNER.parent))
    spec.loader.exec_module(mod)
    return mod


class TestSpark11Record(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(RECORD.read_text(encoding="utf-8"))
        cls.md = MD.read_text(encoding="utf-8")

    def test_runs_as_recorded(self):
        runs = {r["slug"]: r for r in self.doc["runs"]}
        self.assertEqual(
            {k: (v["outcome"], v["tests_before"], v["tests_after"])
             for k, v in runs.items()},
            {"tier1": ("passed", 6, 10), "tier2": ("passed", 6, 9),
             "tier3": ("passed", 6, 9),
             "guardrail": ("escalated", None, None)})
        for r in runs.values():
            self.assertIn("muse-spark-1.1", r["config"])
            self.assertEqual(r["fallback_stats"],
                             {"fallbacks": 0, "fallback_successes": 0})

    def test_every_role_ran_spark11(self):
        for r in self.doc["runs"]:
            if r["slug"] == "guardrail":
                continue
            per_role = r["cost"]["per_role"]
            self.assertEqual(set(per_role),
                             {"TRIAGE", "PLANNER", "CODER", "REVIEWER"})
            for role in per_role.values():
                self.assertEqual(role["models"], ["muse-spark-1.1"])

    def test_summary_recomputes_from_rows(self):
        s = self.doc["summary"]
        work = [r for r in self.doc["runs"] if r["slug"] != "guardrail"]
        self.assertEqual(s["work_tiers_passed"],
                         f"{sum(1 for r in work if r['outcome'] == 'passed')}"
                         f"/{len(work)}")
        self.assertEqual(s["work_tiers_passed"], "3/3")
        self.assertTrue(s["guardrail_escalated"])
        self.assertEqual(s["test_growth"], 10)
        self.assertEqual(s["total_wall_clock_seconds"], 77.67)
        self.assertEqual(s["total_usd_est"], 0.024451)

    def test_markdown_is_runner_render(self):
        self.assertEqual(self.md, _load_runner().render_md(self.doc))


if __name__ == "__main__":
    unittest.main()
