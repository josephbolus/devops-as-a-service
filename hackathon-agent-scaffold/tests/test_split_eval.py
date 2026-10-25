"""Per-role model split experiment (maximizer iteration 11).

Pins: the pre-registered decision rule as a pure function (synthetic
summaries, no API call); the committed split-runs.json record (split
config, per-role models actually recorded on the live runs, guardrail
at 0 model calls); and that the recorded decision is exactly what the
rule produces from the recorded baseline and split summaries — the
decision cannot be edited in post without this suite failing.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import run_split_eval  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "eval-scorecard" / "split-runs.json"
BASELINE = ROOT / "eval-scorecard" / "live-runs.json"
DOC = ROOT / "META_AI_TOOLING.md"

S = {"pass_count": 4, "total_test_growth": 9,
     "total_wall_clock_seconds": 94.65}


class TestDecisionRule(unittest.TestCase):
    def test_split_wins_on_pass_count(self):
        d = run_split_eval.decide(S, {**S, "pass_count": 5})
        self.assertEqual(d["keep"], "split")
        self.assertEqual(d["decided_on"], "pass_count")

    def test_split_loses_on_pass_count(self):
        d = run_split_eval.decide(S, {**S, "pass_count": 3})
        self.assertEqual(d["keep"], "uniform")

    def test_tie_on_pass_split_wins_on_growth(self):
        d = run_split_eval.decide(S, {**S, "total_test_growth": 12})
        self.assertEqual(d["keep"], "split")
        self.assertEqual(d["decided_on"], "total_test_growth")

    def test_tie_on_pass_split_loses_on_growth(self):
        d = run_split_eval.decide(S, {**S, "total_test_growth": 5})
        self.assertEqual(d["keep"], "uniform")

    def test_tie_through_growth_split_wins_on_wall_clock(self):
        d = run_split_eval.decide(S, {**S,
                                      "total_wall_clock_seconds": 80.0})
        self.assertEqual(d["keep"], "split")
        self.assertEqual(d["decided_on"], "total_wall_clock_seconds")

    def test_tie_through_growth_split_loses_on_wall_clock(self):
        d = run_split_eval.decide(S, {**S,
                                      "total_wall_clock_seconds": 120.0})
        self.assertEqual(d["keep"], "uniform")

    def test_full_tie_keeps_uniform(self):
        d = run_split_eval.decide(S, dict(S))
        self.assertEqual(d["keep"], "uniform")
        self.assertEqual(d["decided_on"], "full tie")

    def test_split_config_is_the_registered_one(self):
        self.assertEqual(run_split_eval.SPLIT_ROLE_MODELS,
                         {"CODER": "muse-wonder-1.0",
                          "REVIEWER": "muse-wonder-1.0"})
        self.assertEqual(run_split_eval.DEFAULT_MODEL, "muse-spark-1.3")


class TestCommittedRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(RECORD.read_text())
        cls.runs = {r["slug"]: r for r in cls.doc["runs"]}

    def test_config_and_rule_recorded(self):
        cfg = self.doc["split_config"]
        self.assertEqual(cfg["CODER"], "muse-wonder-1.0")
        self.assertEqual(cfg["REVIEWER"], "muse-wonder-1.0")
        self.assertIn("muse-spark-1.3", cfg["TRIAGE"])
        self.assertIn("pass count", self.doc[
            "decision_rule_registered_before_runs"])

    def test_work_runs_record_actual_models_per_role(self):
        for slug in ("tier1", "tier2", "tier3"):
            with self.subTest(slug=slug):
                models = self.runs[slug]["models_by_role"]
                self.assertEqual(models["CODER"], "muse-wonder-1.0")
                self.assertEqual(models["REVIEWER"], "muse-wonder-1.0")
                self.assertEqual(models["TRIAGE"], "muse-spark-1.3")
                self.assertEqual(models["PLANNER"], "muse-spark-1.3")
                self.assertEqual(self.runs[slug]["model_calls"], 4)

    def test_guardrail_escalated_with_zero_model_calls(self):
        g = self.runs["guardrail"]
        self.assertEqual(g["outcome"], "escalated")
        self.assertTrue(g["correct"])
        self.assertEqual(g["model_calls"], 0)
        self.assertTrue(g["approval_request_written"])

    def test_recorded_decision_matches_the_rule(self):
        baseline = json.loads(BASELINE.read_text())
        b_work = [r for r in baseline["runs"] if r["slug"] != "guardrail"]
        b_guard = [r for r in baseline["runs"]
                   if r["slug"] == "guardrail"][0]
        b_summary = {
            "pass_count": sum(1 for r in b_work if r["correct"])
                          + (1 if b_guard["correct"] else 0),
            "total_test_growth": sum(
                r["tests_after"] - r["tests_before"]
                for r in b_work if r["correct"]),
            "total_wall_clock_seconds":
                baseline["summary"]["total_wall_clock_seconds"],
        }
        expected = run_split_eval.decide(b_summary, self.doc["summary"])
        self.assertEqual(self.doc["decision"]["keep"],
                         expected["keep"])
        self.assertEqual(self.doc["decision"]["decided_on"],
                         expected["decided_on"])
        self.assertEqual(self.doc["uniform_baseline"]["summary"]
                         ["total_wall_clock_seconds"],
                         b_summary["total_wall_clock_seconds"])

    def test_tooling_doc_records_the_experiment(self):
        text = DOC.read_text(encoding="utf-8")
        for token in ("muse-wonder-1.0", "split-runs.json",
                      "Per-role split: experiment run, decision recorded"):
            self.assertIn(token, text, token)


if __name__ == "__main__":
    unittest.main()
