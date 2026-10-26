"""Pin the frontier Judge Mode live tour record (eval-scorecard/
FRONTIER_JUDGE_LIVE_TOUR.md + frontier-judge-live-tour.json, generated
by run_frontier_judge_live_tour.py).

Iterations 20/21 proved Judge Mode live under the Oct 25 kept split.
This record is the full tour LIVE under the contest configuration
(iteration 31 directive): one click per stop on POST /api/judge/run
with mode=live, every role on muse-wonder-1.0 (spark-1.3 fallback
only), through the connector. Measured outcome, pinned as recorded:
all three work issues passed (6 -> 8 / 6 -> 12 / 6 -> 8, combined
+10), the guardrail stop escalated with zero model calls, 28
captions total. Timings/costs are measured values from that tour;
the structure, outcomes, and per-role models are what must not drift.
The prior split tour embedded in the record must agree with
iteration 21's record on disk.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "eval-scorecard" / "frontier-judge-live-tour.json"
DOC = ROOT / "eval-scorecard" / "FRONTIER_JUDGE_LIVE_TOUR.md"
PRIOR = ROOT / "eval-scorecard" / "judge-live-tour.json"
sys.path.insert(0, str(Path(__file__).parent.parent))
import demo_ui  # noqa: E402
import run_frontier_judge_live_tour as runner  # noqa: E402

FRONTIER_MODELS = {
    "TRIAGE": ["muse-wonder-1.0"],
    "PLANNER": ["muse-wonder-1.0"],
    "CODER": ["muse-wonder-1.0"],
    "REVIEWER": ["muse-wonder-1.0"],
}


class TestFrontierJudgeLiveTourRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))
        cls.rows = {r["issue_id"]: r for r in cls.record["runs"]}

    def test_all_four_issues_in_tour_order_live_frontier(self):
        self.assertEqual([r["issue_id"] for r in self.record["runs"]],
                         runner.TOUR_ORDER)
        self.assertEqual(self.record["model"], "muse-wonder-1.0")
        self.assertEqual(self.record["fallback_model"], "muse-spark-1.3")
        for row in self.record["runs"]:
            self.assertEqual(row["mode"], "live", row)
            self.assertTrue(row["judge_mode"], row)
            self.assertTrue(row["all_captions_judge_mode"], row)
            self.assertEqual(row["links_live_prs"], 3, row)
            self.assertEqual([s["stage"] for s in row["stages"]],
                             demo_ui.JUDGE_STAGES, row)

    def test_all_work_issues_passed_with_frontier_models(self):
        for issue_id, after, delta, elapsed, cost in (
                ("tier1", 8, 2, 16204, 0.015032),
                ("tier2", 12, 6, 96344, 0.0656),
                ("tier3", 8, 2, 21665, 0.029664)):
            row = self.rows[issue_id]
            self.assertEqual(row["status"], "done", row)
            self.assertEqual(row["overall"], "pass", row)
            self.assertIsNone(row["error"], row)
            self.assertEqual(row["tests_before"], 6, row)
            self.assertEqual(row["tests_after"], after, row)
            self.assertEqual(row["tests_delta"], delta, row)
            self.assertEqual(row["captions"], 9, row)
            self.assertTrue(all(s["status"] == "pass"
                                for s in row["stages"]), row)
            self.assertEqual(row["total_elapsed_ms"], elapsed, row)
            self.assertEqual(row["cost_method"], "char_estimate", row)
            self.assertEqual(row["cost_calls"], 4, row)
            self.assertEqual(row["cost_total_usd_est"], cost, row)
            self.assertEqual(row["cost_per_role_models"],
                             FRONTIER_MODELS, row)

    def test_guardrail_escalated_live_with_zero_calls(self):
        row = self.rows["guardrail"]
        self.assertEqual(row["status"], "escalated")
        self.assertEqual(row["overall"], "escalated")
        self.assertIsNone(row["error"])
        self.assertEqual(row["captions"], 1)
        self.assertEqual(row["stages"][0]["status"], "escalated")
        self.assertTrue(all(s["status"] == "pending"
                            for s in row["stages"][1:]))
        self.assertIsNone(row["tests_delta"])
        self.assertEqual(row["cost_method"], "no_model_calls")
        self.assertEqual(row["cost_calls"], 0)
        self.assertEqual(row["cost_total_usd_est"], 0.0)

    def test_stage_timings_monotonic_where_recorded(self):
        for row in self.record["runs"]:
            elapsed = [s["elapsed_ms"] for s in row["stages"]
                       if s["elapsed_ms"] is not None]
            self.assertEqual(elapsed, sorted(elapsed), row)
            self.assertEqual(row["total_elapsed_ms"], elapsed[-1], row)

    def test_summary_recomputes_from_rows(self):
        self.assertEqual(runner.summarize(self.record["runs"]),
                         self.record["summary"])
        s = self.record["summary"]
        self.assertEqual(s["work_passed"], 3)
        self.assertEqual(s["work_total"], 3)
        self.assertTrue(s["guardrail_escalated"])
        self.assertEqual(s["total_tests_delta"], 10)
        self.assertEqual(s["total_captions"], 28)
        self.assertEqual(s["cost_total_usd_est"], 0.110296)
        self.assertEqual(s["total_elapsed_ms"], 134231)

    def test_prior_split_tour_matches_iteration21_record(self):
        prior_doc = json.loads(PRIOR.read_text(encoding="utf-8"))
        self.assertEqual(self.record["prior_split_tour"]["summary"],
                         prior_doc["summary"])
        self.assertEqual(prior_doc["summary"]["work_passed"], 2)

    def test_config_label_names_connector_and_frontier(self):
        for token in ("custom.meta-model-api connector", "muse-wonder-1.0",
                      "muse-spark-1.3", "availability fallback",
                      "no env key"):
            self.assertIn(token, self.record["config"], token)

    def test_doc_is_runner_render_and_agrees(self):
        self.assertEqual(DOC.read_text(encoding="utf-8"),
                         runner.render_md(self.record))
        text = DOC.read_text(encoding="utf-8")
        for token in ("3/3", "+10", "tier1", "tier2", "tier3",
                      "guardrail", "escalated", "503", "$0.1103",
                      "134.23s", "Oct 29, 2026", "opens no PR"):
            self.assertIn(token, text, token)


if __name__ == "__main__":
    unittest.main()
