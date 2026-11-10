"""Guardrail unit tests: every reason, the fixed check order, and the
pass case. The guardrail is deterministic, so these expectations are exact.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from approvetopay import guardrail

POLICY = {"category_allowlist": ["hardware", "software", "office_supplies"],
          "currency": "USD"}


def job(category="hardware", quoted="100.00", checkout="100.00", cap="200.00"):
    return {"category": category, "quoted_price": quoted,
            "checkout_price": checkout, "budget_cap": cap}


class TestGuardrail(unittest.TestCase):
    def test_clean_job_passes(self):
        v = guardrail.check(job(), POLICY)
        self.assertTrue(v.passed)
        self.assertIsNone(v.reason)

    def test_disallowed_category_blocks(self):
        v = guardrail.check(job(category="gift_cards"), POLICY)
        self.assertFalse(v.passed)
        self.assertEqual(v.reason, "category_not_allowed")

    def test_over_budget_quoted_blocks(self):
        v = guardrail.check(job(quoted="250.00", checkout="250.00"), POLICY)
        self.assertEqual(v.reason, "over_budget")

    def test_price_increase_blocks_as_price_changed(self):
        v = guardrail.check(job(quoted="100.00", checkout="120.00"), POLICY)
        self.assertEqual(v.reason, "price_changed")

    def test_price_decrease_also_blocks(self):
        # The captured amount must equal the quoted/approved amount; any
        # drift, even in the buyer's favor, goes back for re-approval.
        v = guardrail.check(job(quoted="100.00", checkout="80.00"), POLICY)
        self.assertEqual(v.reason, "price_changed")

    def test_price_drift_reported_even_when_checkout_still_under_cap(self):
        v = guardrail.check(job(quoted="179.99", checkout="214.99", cap="250.00"),
                            POLICY)
        self.assertEqual(v.reason, "price_changed")

    def test_exactly_at_cap_passes(self):
        v = guardrail.check(job(quoted="200.00", checkout="200.00"), POLICY)
        self.assertTrue(v.passed)

    def test_one_cent_over_cap_blocks(self):
        v = guardrail.check(job(quoted="200.01", checkout="200.01"), POLICY)
        self.assertEqual(v.reason, "over_budget")

    def test_category_checked_before_budget(self):
        v = guardrail.check(job(category="crypto", quoted="999.00",
                                checkout="999.00", cap="10.00"), POLICY)
        self.assertEqual(v.reason, "category_not_allowed")

    def test_deterministic_same_input_same_verdict(self):
        j = job(quoted="100.00", checkout="101.00")
        self.assertEqual(guardrail.check(j, POLICY), guardrail.check(j, POLICY))


if __name__ == "__main__":
    unittest.main()
