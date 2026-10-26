"""Pin the expansion batch-3 record (iteration 37): spec issues
#5/#10/#11 seeded as genuine defects and passed live all-frontier.
Batch 3 completes the spec's 12-issue work set."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REC = ROOT / "eval-scorecard" / "expansion-batch3-runs.json"
DOC = ROOT / "eval-scorecard" / "EXPANSION_BATCH3.md"
DEMO = ROOT / "hackathon-demo-repo"


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_expansion_batch3_eval",
        ROOT / "hackathon-agent-scaffold" / "run_expansion_batch3_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestExpansionBatch3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(REC.read_text())
        cls.md = DOC.read_text()

    def test_outcomes_as_recorded(self):
        runs = {r["slug"]: r for r in self.doc["runs"]}
        self.assertEqual(set(runs), {"retry-storm", "deploy-token",
                                     "api-pagination"})
        for slug, r in runs.items():
            self.assertEqual(r["outcome"], "passed", slug)
            self.assertEqual(r["tests_before"], 24, slug)
            self.assertGreater(r["tests_after"], 24, slug)

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
            "from app.retryer import call_with_retry\n"
            "from app.deploy import run_deploy\n"
            "from app.apiclient import fetch_all\n"
            "delays = []\n"
            "calls = [0]\n"
            "def flaky():\n"
            "    calls[0] += 1\n"
            "    if calls[0] < 3: raise RuntimeError('x')\n"
            "    return 'ok'\n"
            "assert call_with_retry(flaky, sleep=delays.append) == 'ok'\n"
            "assert delays == [], delays\n"
            "logs = []\n"
            "try:\n"
            "    run_deploy('tok-expired-123', lambda t: False, logs.append)\n"
            "    raise AssertionError('should have raised')\n"
            "except RuntimeError as e:\n"
            "    assert 'tok-expired-123' in str(e)\n"
            "assert any('tok-expired-123' in l for l in logs)\n"
            "pages = {1: {'items': [1, 2], 'next_page': 2},\n"
            "         2: {'items': [3], 'next_page': None}}\n"
            "assert fetch_all(lambda p: pages[p]) == [1, 2]\n"
        )
        proc = subprocess.run([sys.executable, "-c", probe], cwd=DEMO,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
