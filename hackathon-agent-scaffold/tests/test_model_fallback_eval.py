"""Pin the model-fallback live record (iteration 28).

The record (eval-scorecard/model-fallback-runs.json + MODEL_FALLBACK.md)
must stay internally consistent: probes, the controlled live fallback
exercise, and the fallback-config pipeline runs are recomputed from
the rows, and the markdown must be exactly the runner's render of the
JSON — a stale or hand-edited summary fails here.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "eval-scorecard" / "model-fallback-runs.json"
MD = ROOT / "eval-scorecard" / "MODEL_FALLBACK.md"
RUNNER = ROOT / "hackathon-agent-scaffold" / "run_model_fallback_eval.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("mfe", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(RUNNER.parent))
    spec.loader.exec_module(mod)
    return mod


class TestModelFallbackRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(RECORD.read_text(encoding="utf-8"))
        cls.md = MD.read_text(encoding="utf-8")

    def test_probes_all_four_models_ok(self):
        probes = {p["model"]: p for p in self.doc["probes"]}
        self.assertEqual(set(probes), {"muse-spark-1.3", "muse-wonder-1.0",
                                       "muse-spark-1.2", "muse-spark-1.1"})
        self.assertTrue(all(p["ok"] for p in probes.values()))
        self.assertEqual(self.doc["summary"]["probes_ok"], "4/4")

    def test_fallback_exercise_fired_live(self):
        ex = self.doc["fallback_exercise"]
        self.assertTrue(ex["controlled_probe"])
        self.assertEqual(ex["primary_model"],
                         "muse-spark-0.0-does-not-exist")
        self.assertEqual(ex["fallback_model"], "muse-spark-1.2")
        self.assertTrue(ex["ok"])
        self.assertEqual(ex["fallback_stats"],
                         {"fallbacks": 1, "fallback_successes": 1})
        self.assertEqual(ex["retry_stats"]["calls"], 2)

    def test_fallback_config_runs_as_recorded(self):
        runs = {r["slug"]: r for r in self.doc["runs"]}
        self.assertEqual(
            {k: (v["outcome"], v["tests_before"], v["tests_after"])
             for k, v in runs.items()},
            {"tier1": ("passed", 6, 13), "tier2": ("passed", 6, 14),
             "tier3": ("passed", 6, 11),
             "guardrail": ("escalated", None, None)})
        for r in runs.values():
            self.assertIn("muse-spark-1.2", r["config"])
            self.assertEqual(r["fallback_stats"],
                             {"fallbacks": 0, "fallback_successes": 0})

    def test_summary_recomputes_from_rows(self):
        s = self.doc["summary"]
        work = [r for r in self.doc["runs"] if r["slug"] != "guardrail"]
        self.assertEqual(s["work_tiers_passed"],
                         f"{sum(1 for r in work if r['outcome'] == 'passed')}"
                         f"/{len(work)}")
        self.assertEqual(s["work_tiers_passed"], "3/3")
        self.assertTrue(s["guardrail_escalated"])
        self.assertEqual(s["test_growth"], 20)
        self.assertEqual(s["total_wall_clock_seconds"], 88.59)

    def test_markdown_is_runner_render(self):
        self.assertEqual(self.md, _load_runner().render_md(self.doc))


if __name__ == "__main__":
    unittest.main()
