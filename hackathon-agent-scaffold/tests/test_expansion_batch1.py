"""Pin the expansion batch-1 record (iteration 35): spec issues
#4/#8/#9 seeded as genuine defects and passed live all-frontier."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REC = ROOT / "eval-scorecard" / "expansion-batch1-runs.json"
DOC = ROOT / "eval-scorecard" / "EXPANSION_BATCH1.md"
DEMO = ROOT / "hackathon-demo-repo"


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_expansion_batch1_eval",
        ROOT / "hackathon-agent-scaffold" / "run_expansion_batch1_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestExpansionBatch1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(REC.read_text())
        cls.md = DOC.read_text()

    def test_outcomes_as_recorded(self):
        runs = {r["slug"]: r for r in self.doc["runs"]}
        self.assertEqual(set(runs), {"config-drift", "health-check",
                                     "alert-threshold"})
        for slug, r in runs.items():
            self.assertEqual(r["outcome"], "passed", slug)
            self.assertEqual(r["tests_before"], 12, slug)
            self.assertGreater(r["tests_after"], 12, slug)

    def test_every_role_used_frontier_model(self):
        for role, models in self.doc["per_role_models"].items():
            self.assertEqual(models, ["muse-wonder-1.0"], role)
        self.assertEqual(set(self.doc["per_role_models"]),
                         {"TRIAGE", "PLANNER", "CODER", "REVIEWER"})

    def test_no_fallback_or_retry_fired(self):
        for r in self.doc["runs"]:
            self.assertEqual(r["fallback_stats"]["fallbacks"], 0, r["slug"])
            self.assertEqual(r["retry_stats"]["retries"], 0, r["slug"])

    def test_summary_recomputes(self):
        s = self.doc["summary"]
        passed = [r for r in self.doc["runs"] if r["outcome"] == "passed"]
        growth = sum(r["tests_after"] - r["tests_before"] for r in passed)
        self.assertEqual(s["test_growth"], growth)
        self.assertEqual(s["issues_passed"],
                         f"{len(passed)}/{len(self.doc['runs'])}")
        total = round(sum((r["cost"] or {}).get("total_usd_est", 0.0)
                          for r in self.doc["runs"]), 6)
        self.assertEqual(s["total_usd_est"], total)

    def test_doc_matches_runner_render(self):
        self.assertEqual(self.md, _load_runner().render_md(self.doc))

    def test_vendored_defects_still_present(self):
        # Subprocess: importing the demo `app` package in-process would
        # poison sys.modules for tests that run the pipeline on copies.
        import subprocess
        import sys
        probe = (
            "from app.config import load_config\n"
            "from app.health import overall_status\n"
            "from app.alerts import should_page\n"
            "assert load_config({'APP_PORT': '9090'})['port'] == 8080\n"
            "checks = [{'name': 'database', 'ok': False, 'critical': True},"
            " {'name': 'cache', 'ok': True, 'critical': False}]\n"
            "assert overall_status(checks) == 'healthy'\n"
            "assert should_page('latency_ms', 100, 500) is True\n"
            "assert should_page('latency_ms', 900, 500) is False\n"
        )
        proc = subprocess.run([sys.executable, "-c", probe], cwd=DEMO,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
