"""Pin the frontier eval record (iteration 31): all roles on muse-wonder-1.0.

Joseph's Oct 26 directive made the contest configuration all-frontier.
This test recomputes the summary from the written record
(eval-scorecard/frontier-runs.json, the authoritative artifact) and
pins that every role's calls used muse-wonder-1.0, the guardrail
escalated, and the doc carries the measured numbers.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REC = ROOT / "eval-scorecard" / "frontier-runs.json"
DOC = ROOT / "eval-scorecard" / "FRONTIER.md"


class TestFrontierEval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(REC.read_text())
        cls.md = DOC.read_text()

    def test_outcomes_as_recorded(self):
        runs = {r["slug"]: r for r in self.doc["runs"]}
        self.assertEqual(runs["tier1"]["outcome"], "passed")
        self.assertEqual(runs["tier2"]["outcome"], "passed")
        self.assertEqual(runs["tier3"]["outcome"], "passed")
        self.assertEqual(runs["guardrail"]["outcome"], "escalated")

    def test_every_role_used_frontier_model(self):
        for role, models in self.doc["per_role_models"].items():
            self.assertEqual(models, ["muse-wonder-1.0"], role)
        self.assertEqual(set(self.doc["per_role_models"]),
                         {"TRIAGE", "PLANNER", "CODER", "REVIEWER"})

    def test_no_fallback_fired(self):
        for r in self.doc["runs"]:
            self.assertEqual(r["fallback_stats"]["fallbacks"], 0, r["slug"])

    def test_summary_recomputes(self):
        s = self.doc["summary"]
        work = [r for r in self.doc["runs"] if r["slug"] != "guardrail"]
        passed = [r for r in work if r["outcome"] == "passed"]
        growth = sum(r["tests_after"] - r["tests_before"] for r in passed)
        self.assertEqual(s["test_growth"], growth)
        self.assertEqual(s["work_tiers_passed"], f"{len(passed)}/{len(work)}")
        self.assertAlmostEqual(
            s["total_wall_clock_seconds"],
            round(sum(r["wall_clock_seconds"] for r in self.doc["runs"]), 2),
            places=1)
        total = round(sum((r["cost"] or {}).get("total_usd_est", 0.0)
                          for r in self.doc["runs"]), 6)
        self.assertEqual(s["total_usd_est"], total)

    def test_doc_carries_measured_numbers(self):
        s = self.doc["summary"]
        for token in ("muse-wonder-1.0", "muse-wonder-1.1",
                      f"+{s['test_growth']}",
                      f"{s['total_wall_clock_seconds']}s",
                      "availability fallbacks"):
            self.assertIn(token, self.md, token)


if __name__ == "__main__":
    unittest.main()
