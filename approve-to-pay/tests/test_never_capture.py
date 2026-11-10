"""The never-capture-on-no invariant, and its guardrail twin.

These are the two money-safety properties the whole product rests on:

1. Console approver says "deny"  =>  capture() is NEVER called, the
   decision log says capture_called: false, and $0 moves.
2. Guardrail blocks a job  =>  no order is even created, and capture()
   is never called.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from approvetopay import pipeline
from approvetopay.decision_log import DecisionLog
from approvetopay.paypal_client import MockPayPalClient

POLICY = {"category_allowlist": ["hardware", "software"], "currency": "USD"}


def job(**overrides):
    base = {"id": "ATP-T01", "title": "test job", "item": "thing",
            "category": "hardware", "quoted_price": "100.00",
            "checkout_price": "100.00", "budget_cap": "200.00",
            "approver_decision": "approve", "expected_outcome": "capture",
            "expected_reason": None}
    base.update(overrides)
    return base


class TestNeverCaptureOnNo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = DecisionLog(Path(self.tmp.name) / "log.jsonl")
        self.client = MockPayPalClient()

    def tearDown(self):
        self.tmp.cleanup()

    def test_approver_deny_never_calls_capture(self):
        entry = pipeline.run_job(job(approver_decision="deny",
                                     expected_outcome="block_approver"),
                                 POLICY, self.client, self.log, "run-test")
        self.assertEqual(self.client.capture_calls, [])
        self.assertFalse(entry["capture_called"])
        self.assertIsNone(entry["capture_status"])
        self.assertEqual(entry["actual_outcome"], "block_approver")
        # The order was created and left UNCAPTURED — that is the point.
        self.assertIsNotNone(entry["order_id"])
        self.assertEqual(entry["payer_approval"], "approved")

    def test_guardrail_block_creates_no_order_and_never_captures(self):
        entry = pipeline.run_job(job(category="crypto",
                                     expected_outcome="block_guardrail"),
                                 POLICY, self.client, self.log, "run-test")
        self.assertEqual(self.client.created_orders, [])
        self.assertEqual(self.client.capture_calls, [])
        self.assertIsNone(entry["order_id"])
        self.assertFalse(entry["capture_called"])
        self.assertEqual(entry["approver_decision"], "not_reached")

    def test_approve_path_captures_exactly_once(self):
        entry = pipeline.run_job(job(), POLICY, self.client, self.log, "run-test")
        self.assertEqual(len(self.client.capture_calls), 1)
        self.assertTrue(entry["capture_called"])
        self.assertEqual(entry["capture_status"], "COMPLETED")
        self.assertEqual(entry["actual_outcome"], "capture")

    def test_log_is_append_only_across_runs(self):
        pipeline.run_job(job(), POLICY, self.client, self.log, "run-1")
        pipeline.run_job(job(approver_decision="deny",
                             expected_outcome="block_approver"),
                           POLICY, self.client, self.log, "run-2")
        entries = self.log.read_all()
        self.assertEqual(len(entries), 2)
        self.assertEqual([e["run_id"] for e in entries], ["run-1", "run-2"])


if __name__ == "__main__":
    unittest.main()
