"""Frozen task-set integrity: the set the runner measures against must be
the set that was frozen — 20 jobs, unique ids, the declared composition,
and a checksum that still matches tasks.sha256.
"""
import hashlib
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


class TestFrozenTaskSet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / "tasks.json").read_bytes()
        cls.data = json.loads(cls.raw)

    def test_checksum_matches(self):
        recorded = (ROOT / "tasks.sha256").read_text().split()[0]
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), recorded)

    def test_twenty_jobs_unique_ids(self):
        jobs = self.data["jobs"]
        self.assertEqual(len(jobs), 20)
        self.assertEqual(len({j["id"] for j in jobs}), 20)

    def test_composition_matches_declaration(self):
        counts = Counter()
        for j in self.data["jobs"]:
            counts[(j["expected_outcome"], j["expected_reason"])] += 1
        self.assertEqual(counts[("capture", None)], 8)
        self.assertEqual(counts[("block_guardrail", "over_budget")], 4)
        self.assertEqual(counts[("block_guardrail", "category_not_allowed")], 3)
        self.assertEqual(counts[("block_guardrail", "price_changed")], 3)
        self.assertEqual(counts[("block_approver", "approver_denied")], 2)

    def test_every_job_has_the_fields_the_pipeline_needs(self):
        required = {"id", "title", "item", "merchant", "category",
                    "quoted_price", "checkout_price", "budget_cap",
                    "approver_decision", "expected_outcome", "expected_reason"}
        for j in self.data["jobs"]:
            self.assertTrue(required <= set(j), j["id"])
            self.assertIn(j["approver_decision"], ("approve", "deny"))


if __name__ == "__main__":
    unittest.main()
