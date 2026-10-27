"""Pin the frontier approve-and-resume live record (iteration 47).

The record (eval-scorecard/frontier-resume-runs.json + FRONTIER_RESUME.md)
must stay internally consistent: five pre-registered human-gate flows
run LIVE under the all-frontier contest configuration at the 24-test
baseline were handled 5/5; the four zero-call flows made no model
calls (and left the repo unchanged where that is defined); the live
rescope passed with test growth and muse-wonder-1.0 on every role;
and the markdown is exactly the runner's render of the JSON.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "eval-scorecard" / "frontier-resume-runs.json"
MD = ROOT / "eval-scorecard" / "FRONTIER_RESUME.md"
RUNNER = ROOT / "hackathon-agent-scaffold" / "run_frontier_resume_eval.py"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(mod)
    return mod


class TestFrontierResumeRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(RECORD.read_text(encoding="utf-8"))
        cls.md = MD.read_text(encoding="utf-8")
        cls.flows = {f["slug"]: f for f in cls.doc["flows"]}

    def test_summary_five_of_five(self):
        s = self.doc["summary"]
        self.assertEqual((s["total"], s["handled"]), (5, 5))
        self.assertTrue(s["all_handled"])
        self.assertTrue(s["rescope_passed"])
        self.assertIn("all-frontier", self.doc["config"])
        self.assertIn("muse-wonder-1.0", self.doc["config"])

    def test_zero_call_flows(self):
        expected = {"escalation": "escalated", "reject": "closed_rejected",
                    "handle_manually": "closed_manual",
                    "rescope_still_destructive": "re_escalated"}
        for slug, outcome in expected.items():
            f = self.flows[slug]
            self.assertEqual(f["outcome"], outcome, slug)
            self.assertEqual(f["model_calls"], 0, slug)
            self.assertTrue(f["handled"], slug)
        for slug in ("reject", "handle_manually",
                     "rescope_still_destructive"):
            self.assertTrue(self.flows[slug]["repo_unchanged"], slug)

    def test_rescope_live_passed_with_growth(self):
        f = self.flows["rescope_live"]
        self.assertTrue(f["passed"])
        self.assertEqual(f["tests_before"], 24)
        self.assertGreater(f["tests_after"], 24)
        self.assertEqual(f["unexpected_files"], [])
        self.assertEqual(set(f["models_by_role"].values()),
                         {"muse-wonder-1.0"})
        self.assertEqual(set(f["models_by_role"]),
                         {"TRIAGE", "PLANNER", "CODER", "REVIEWER"})
        self.assertEqual(f["fallback_stats"],
                         {"fallbacks": 0, "fallback_successes": 0})
        self.assertEqual(f["retry_stats"]["retries"], 0)

    def test_totals_recompute(self):
        s = self.doc["summary"]
        live = self.flows["rescope_live"]
        self.assertEqual(s["rescope_tests"],
                         f"{live['tests_before']} -> {live['tests_after']}")
        self.assertAlmostEqual(
            s["total_wall_clock_seconds"],
            round(sum(f["wall_clock_seconds"] for f in self.doc["flows"]), 2),
            places=2)

    def test_doc_matches_runner_render(self):
        runner = _load(RUNNER, "frontier_resume")
        self.assertEqual(self.md, runner.render_md(self.doc))


if __name__ == "__main__":
    unittest.main()
