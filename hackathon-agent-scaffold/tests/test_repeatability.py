"""Repeatability eval (maximizer iteration 14).

Pins: the aggregate() pure function on synthetic runs; the committed
repeat-runs.json record (split replicate 2: per-role models recorded,
guardrail at 0 model calls, 3/3 passed); that the record's combined
blocks are exactly what aggregate() produces from the three committed
records; and that REPEATABILITY.md's numbers match the record.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import run_repeatability_eval as rre  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "eval-scorecard" / "repeat-runs.json"
DOC = ROOT / "REPEATABILITY.md"


def _run(slug, outcome, correct, wall, before=None, after=None):
    return {"slug": slug, "outcome": outcome, "correct": correct,
            "wall_clock_seconds": wall,
            "tests_before": before, "tests_after": after}


class TestAggregate(unittest.TestCase):
    def test_aggregate_counts_and_stats(self):
        sources = [("a", [_run("tier1", "passed", True, 10.0, 6, 9),
                          _run("guardrail", "escalated", True, 0.0)]),
                   ("b", [_run("tier1", "failed", False, 20.0, 6, 6),
                          _run("guardrail", "escalated", True, 0.0)])]
        agg = rre.aggregate(sources)
        self.assertEqual(agg["work_tiers"]["pass_rate"], "1/2")
        self.assertEqual(agg["guardrail"]["pass_rate"], "2/2")
        t1 = agg["per_tier"]["tier1"]
        self.assertEqual(t1["wall_clock"]["mean"], 15.0)
        self.assertEqual(t1["test_growth"]["n"], 1)  # passed runs only
        self.assertEqual(t1["test_growth"]["mean"], 3)

    def test_split_config_is_the_kept_one(self):
        self.assertEqual(rre.SPLIT_ROLE_MODELS,
                         {"CODER": "muse-wonder-1.0",
                          "REVIEWER": "muse-wonder-1.0"})
        self.assertEqual(rre.DEFAULT_MODEL, "muse-spark-1.3")


class TestCommittedRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(RECORD.read_text())
        cls.runs = {r["slug"]: r for r in cls.doc["runs"]}

    def test_replicate2_all_pass_with_actual_models(self):
        self.assertEqual(self.doc["summary"]["work_tiers_passed"], "3/3")
        self.assertTrue(self.doc["summary"]["guardrail_escalated"])
        self.assertEqual(self.doc["summary"]["total_test_growth"], 10)
        self.assertEqual(self.doc["summary"]["total_wall_clock_seconds"], 120.31)
        for slug in ("tier1", "tier2", "tier3"):
            with self.subTest(slug=slug):
                models = self.runs[slug]["models_by_role"]
                self.assertEqual(models["CODER"], "muse-wonder-1.0")
                self.assertEqual(models["REVIEWER"], "muse-wonder-1.0")
                self.assertEqual(models["TRIAGE"], "muse-spark-1.3")
                self.assertEqual(models["PLANNER"], "muse-spark-1.3")
                self.assertEqual(self.runs[slug]["model_calls"], 4)
                self.assertEqual(self.runs[slug]["unexpected_files"], [])

    def test_replicate2_guardrail_zero_calls(self):
        g = self.runs["guardrail"]
        self.assertEqual(g["outcome"], "escalated")
        self.assertTrue(g["correct"])
        self.assertEqual(g["model_calls"], 0)
        self.assertTrue(g["approval_request_written"])

    def test_combined_blocks_recompute_from_the_three_records(self):
        uniform = json.loads((ROOT / "eval-scorecard" / "live-runs.json").read_text())
        split1 = json.loads((ROOT / "eval-scorecard" / "split-runs.json").read_text())
        combined = rre.aggregate([("uniform-1", uniform["runs"]),
                                  ("split-1", split1["runs"]),
                                  ("split-2", self.doc["runs"])])
        self.assertEqual(combined, self.doc["combined_all_live_timed"])
        split_only = rre.aggregate([("split-1", split1["runs"]),
                                    ("split-2", self.doc["runs"])])
        self.assertEqual(split_only, self.doc["combined_split_only"])
        self.assertEqual(combined["work_tiers"]["pass_rate"], "9/9")
        self.assertEqual(combined["guardrail"]["pass_rate"], "3/3")

    def test_doc_numbers_match_the_record(self):
        text = DOC.read_text(encoding="utf-8")
        for token in ("9/9", "3/3", "6/6", "120.31s", "209.14s",
                      "27.9s", "69.04s", "23.37s", "6 → 11",
                      "31.31s", "80.67s", "29.38s", "+10",
                      "repeat-runs.json", "not a model"):
            self.assertIn(token, text, token)


if __name__ == "__main__":
    unittest.main()
