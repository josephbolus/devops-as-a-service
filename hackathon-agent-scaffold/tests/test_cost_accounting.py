"""Per-run cost accounting (daas/cost.py + pipeline + console + record).

Pins: the estimation math and published prices; the honest finding
that API usage is NOT exposed on the connector path (costs are
character-count estimates, labeled as such everywhere); the pipeline
attaching a per-role cost summary to every result (mock = $0 real,
guardrail = $0 with zero calls); the demo console results card
surfacing the cost; and the committed live record
(eval-scorecard/cost-runs.json) agreeing with COST_ACCOUNTING.md and
IMPACT_MODEL.md, with every total recomputed here from the per-call
records rather than trusted.
"""
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import demo_ui  # noqa: E402
from daas import cost, pipeline  # noqa: E402
from daas.llm import MockClient  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SCAFFOLD = Path(__file__).resolve().parent.parent
DEMO_REPO = ROOT / "hackathon-demo-repo"
COST_RUNS = ROOT / "eval-scorecard" / "cost-runs.json"
COST_DOC = ROOT / "eval-scorecard" / "COST_ACCOUNTING.md"
IMPACT_DOC = ROOT / "IMPACT_MODEL.md"


class CostMath(unittest.TestCase):
    def test_prices_are_the_published_rates(self):
        self.assertEqual(cost.PRICES_USD_PER_MTOK["muse-spark-1.3"],
                         {"input": 1.25, "output": 4.25})
        self.assertEqual(cost.PRICES_USD_PER_MTOK["muse-wonder-1.0"],
                         {"input": 4.00, "output": 20.00})
        self.assertEqual(cost.PRICES_USD_PER_MTOK["mock"],
                         {"input": 0.0, "output": 0.0})

    def test_estimate_tokens_rounds_up(self):
        self.assertEqual(cost.estimate_tokens(0), 0)
        self.assertEqual(cost.estimate_tokens(4), 1)
        self.assertEqual(cost.estimate_tokens(5), 2)
        self.assertEqual(cost.estimate_tokens(4000), 1000)

    def test_record_call_estimates_and_prices(self):
        rec = cost.record_call("CODER", "muse-wonder-1.0",
                               "s" * 400, "u" * 3600, "o" * 2000)
        self.assertEqual(rec["method"], "char_estimate")
        self.assertEqual(rec["input_tokens_est"], 1000)
        self.assertEqual(rec["output_tokens_est"], 500)
        # 1000 in @ $4/1M + 500 out @ $20/1M = $0.004 + $0.010
        self.assertAlmostEqual(rec["cost_usd_est"], 0.014, places=6)

    def test_api_usage_wins_when_a_transport_provides_it(self):
        rec = cost.record_call("TRIAGE", "muse-spark-1.3", "x" * 9999,
                               "", "y", usage={"prompt_tokens": 10,
                                               "completion_tokens": 3})
        self.assertEqual(rec["method"], "api_usage")
        self.assertEqual(rec["input_tokens_est"], 10)

    def test_usage_not_exposed_is_documented_in_the_module(self):
        text = Path(cost.__file__).read_text()
        self.assertIn("NOT exposed", text)
        self.assertIn("usage", text)
        self.assertIn("ESTIMATES from character", text)


class PipelineCost(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        shutil.copytree(DEMO_REPO, self.repo,
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.out = self.tmp / "out"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_mock_run_cost_is_zero_and_per_role(self):
        issue = json.loads((SCAFFOLD / "issues" / "tier1.json").read_text())
        result = pipeline.run(self.repo, issue, MockClient(), self.out)
        c = result["cost"]
        self.assertEqual(c["method"], "mock_no_api_call")
        self.assertEqual(c["total_usd_est"], 0.0)
        self.assertEqual(c["calls"], 4)
        self.assertEqual(sorted(c["per_role"]),
                         ["CODER", "PLANNER", "REVIEWER", "TRIAGE"])
        doc = json.loads((self.out / "cost.json").read_text())
        self.assertEqual(doc["summary"]["calls"], 4)
        self.assertEqual(len(doc["calls"]), 4)

    def test_guardrail_escalation_carries_zero_cost(self):
        issue = json.loads((SCAFFOLD / "issues" / "guardrail.json").read_text())
        with self.assertRaises(pipeline.Escalation) as ctx:
            pipeline.run(self.repo, issue, MockClient(), self.out)
        self.assertEqual(ctx.exception.cost["total_usd_est"], 0.0)
        self.assertEqual(ctx.exception.cost["calls"], 0)


class ResultsCardCost(unittest.TestCase):
    def test_card_surfaces_pipeline_cost(self):
        summary = cost.summarize([cost.record_call(
            "TRIAGE", "muse-spark-1.3", "s" * 400, "u" * 400, "o" * 400)])
        snap = {"status": "done",
                "result": {"passed": True, "cost": summary}, "events": []}
        card = demo_ui.results_card(snap)
        self.assertEqual(card["cost"]["total_usd_est"],
                         summary["total_usd_est"])
        self.assertEqual(card["cost"]["method"], "char_estimate")

    def test_escalated_card_cost_is_zero(self):
        snap = {"status": "escalated", "result": None, "events": [
            {"stage": "guardrail", "data": {"blocked": True,
                                             "reason": "x"},
             "elapsed_ms": 1}]}
        card = demo_ui.results_card(snap)
        self.assertEqual(card["cost"]["total_usd_est"], 0.0)
        self.assertEqual(card["cost"]["method"], "no_model_calls")

    def test_page_renders_cost(self):
        self.assertIn("card.cost", demo_ui.PAGE)
        self.assertIn("Est. API cost", demo_ui.PAGE)


class LiveCostRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(COST_RUNS.read_text())
        cls.runs = {r["slug"]: r for r in cls.doc["runs"]}

    def test_record_covers_all_tiers_and_guardrail(self):
        self.assertEqual(sorted(self.runs),
                         ["guardrail", "tier1", "tier2", "tier3"])
        self.assertEqual(self.doc["summary"]["method"], "char_estimate")
        self.assertIn("ESTIMATES", self.doc["method"])
        self.assertIn("not exposed", self.doc["method"]
                      + self.doc["record"] + COST_DOC.read_text())

    def test_totals_recompute_from_per_call_records(self):
        for slug, row in self.runs.items():
            with self.subTest(slug=slug):
                calls = row["cost_calls"]
                self.assertEqual(row["cost"]["calls"], len(calls))
                self.assertAlmostEqual(
                    row["cost"]["total_usd_est"],
                    round(sum(c["cost_usd_est"] for c in calls), 6),
                    places=6)
                for c in calls:
                    self.assertAlmostEqual(
                        c["cost_usd_est"],
                        cost.call_cost_usd(c["model"], c["input_tokens_est"],
                                           c["output_tokens_est"]),
                        places=6)
        work = [r for r in self.runs.values() if r["slug"] != "guardrail"]
        passed = [r for r in work if r["outcome"] == "passed"]
        self.assertAlmostEqual(
            self.doc["summary"]["cost_per_passed_issue_usd_est"],
            round(sum(r["cost"]["total_usd_est"] for r in passed)
                  / len(passed), 6), places=6)

    def test_split_models_recorded_per_role(self):
        for slug in ("tier1", "tier2", "tier3"):
            models = {c["role"]: c["model"]
                      for c in self.runs[slug]["cost_calls"]}
            self.assertEqual(models["CODER"], "muse-wonder-1.0", slug)
            self.assertEqual(models["REVIEWER"], "muse-wonder-1.0", slug)
            self.assertEqual(models["TRIAGE"], "muse-spark-1.3", slug)
            self.assertEqual(models["PLANNER"], "muse-spark-1.3", slug)

    def test_guardrail_cost_zero_no_calls(self):
        g = self.runs["guardrail"]
        self.assertEqual(g["outcome"], "escalated")
        self.assertEqual(g["cost"]["total_usd_est"], 0.0)
        self.assertEqual(g["cost_calls"], [])

    def test_docs_agree_with_the_record(self):
        per_passed = self.doc["summary"]["cost_per_passed_issue_usd_est"]
        total = self.doc["summary"]["total_usd_est"]
        for doc_path in (COST_DOC, IMPACT_DOC):
            text = doc_path.read_text()
            self.assertIn(f"${per_passed:.4f}", text, doc_path.name)
            self.assertIn("estimate", text.lower(), doc_path.name)
        self.assertIn(f"${total:.4f}", COST_DOC.read_text())
        # Cost per senior-hour saved, from IMPACT_MODEL's 50 min/pass:
        per_hour = per_passed / (50 / 60)
        self.assertIn(f"${per_hour:.4f}", IMPACT_DOC.read_text())


if __name__ == "__main__":
    unittest.main()
