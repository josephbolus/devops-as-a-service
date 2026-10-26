"""Pin the expansion batch-2 record (iteration 36): spec issues
#6/#7/#12 seeded as genuine defects and passed live all-frontier."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REC = ROOT / "eval-scorecard" / "expansion-batch2-runs.json"
DOC = ROOT / "eval-scorecard" / "EXPANSION_BATCH2.md"
DEMO = ROOT / "hackathon-demo-repo"


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_expansion_batch2_eval",
        ROOT / "hackathon-agent-scaffold" / "run_expansion_batch2_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestExpansionBatch2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(REC.read_text())
        cls.md = DOC.read_text()

    def test_outcomes_as_recorded(self):
        runs = {r["slug"]: r for r in self.doc["runs"]}
        self.assertEqual(set(runs), {"connection-pool", "log-rotation",
                                     "scheduled-job"})
        for slug, r in runs.items():
            self.assertEqual(r["outcome"], "passed", slug)
            self.assertEqual(r["tests_before"], 18, slug)
            self.assertGreater(r["tests_after"], 18, slug)

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
            "import tempfile\n"
            "from pathlib import Path\n"
            "from app.pool import ConnectionPool\n"
            "from app.logwriter import LogWriter\n"
            "from app.scheduler import run_once\n"
            "p = ConnectionPool(max_size=1)\n"
            "try:\n"
            "    p.run(lambda c: 1/0)\n"
            "except ZeroDivisionError:\n"
            "    pass\n"
            "assert p.in_use == 1, p.in_use\n"
            "with tempfile.TemporaryDirectory() as d:\n"
            "    w = LogWriter(Path(d) / 'x.log', max_bytes=10)\n"
            "    w.write('12345678'); w.write('more')\n"
            "    assert w.current_size() == 14\n"
            "    assert not (Path(d) / 'x.log.1').exists()\n"
            "state = {}\n"
            "def bad(): raise RuntimeError('transient')\n"
            "assert run_once(state, '2026-10-26', bad) == 'ran'\n"
            "assert state.get('last_completed') == '2026-10-26'\n"
        )
        proc = subprocess.run([sys.executable, "-c", probe], cwd=DEMO,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
