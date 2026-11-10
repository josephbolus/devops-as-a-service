"""Approval console: smoke tests over real HTTP, plus the interactive
gate end to end — the console pauses with the order UNCAPTURED, the
approver clicks, and only an Approve ever reaches capture.

These tests drive the actual server (stdlib http.server on an ephemeral
port) against a temporary decision log, so the module's real
decision-log.jsonl is never touched by tests.
"""
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from approvetopay.console import make_server
from approvetopay.decision_log import DecisionLog


class ConsoleTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmp.name) / "decision-log.jsonl"
        self.server = make_server("127.0.0.1", 0, self.log_path)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    # -- tiny HTTP helpers -------------------------------------------------
    def get(self, path):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if r.headers.get_content_type()
                              == "application/json" else body)

    def post(self, path, payload):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def wait_for(self, pred, what, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            _, session = self.get("/api/session")
            if pred(session):
                return session
            time.sleep(0.05)
        self.fail(f"timed out waiting for {what}: {session}")

    # -- smoke ---------------------------------------------------------------
    def test_page_is_served(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("Approve-to-Pay", body)
        self.assertIn("Console approval", body)
        self.assertIn("UNCAPTURED", body)

    def test_jobs_endpoint_lists_frozen_set_in_mock_mode(self):
        status, data = self.get("/api/jobs")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["jobs"]), 20)
        # No sandbox credentials in the test environment: the console
        # must label itself SANDBOX-FIXTURE rather than pretend live.
        self.assertEqual(data["mode"]["mode"], "mock")
        self.assertEqual(data["mode"]["label"], "SANDBOX-FIXTURE")

    # -- the interactive gate --------------------------------------------------
    def test_deny_at_the_gate_never_captures(self):
        # ATP-019's scripted decision in the frozen set is "deny", but the
        # console human decides live — here they deny it themselves.
        status, resp = self.post("/api/run", {"job_id": "ATP-019"})
        self.assertEqual(status, 200)
        session = self.wait_for(
            lambda s: s.get("status") == "awaiting_console",
            "the gate to open")
        # The order exists and is still uncaptured while the human decides.
        self.assertEqual(session["order_id"], "MOCK-ATP-019")
        self.assertEqual(session["order_status"], "CREATED")

        status, resp = self.post("/api/decide", {"decision": "deny"})
        self.assertEqual(status, 200)
        session = self.wait_for(lambda s: s.get("status") == "done",
                                "the run to finish")
        entry = session["entry"]
        self.assertEqual(entry["actual_outcome"], "block_approver")
        self.assertFalse(entry["capture_called"])
        self.assertIsNone(entry["capture_status"])
        # And the append-only log carries the proof.
        logged = DecisionLog(self.log_path).read_all()
        self.assertEqual(len(logged), 1)
        self.assertFalse(logged[0]["capture_called"])

    def test_approve_at_the_gate_captures(self):
        self.post("/api/run", {"job_id": "ATP-001"})
        self.wait_for(lambda s: s.get("status") == "awaiting_console",
                      "the gate to open")
        self.post("/api/decide", {"decision": "approve"})
        session = self.wait_for(lambda s: s.get("status") == "done",
                                "the run to finish")
        entry = session["entry"]
        self.assertEqual(entry["actual_outcome"], "capture")
        self.assertTrue(entry["capture_called"])
        self.assertEqual(entry["capture_status"], "COMPLETED")

    def test_guardrail_block_never_opens_the_gate(self):
        self.post("/api/run", {"job_id": "ATP-013"})  # gift cards: not allowed
        session = self.wait_for(lambda s: s.get("status") == "done",
                                "the run to finish without a decision")
        entry = session["entry"]
        self.assertEqual(entry["actual_outcome"], "block_guardrail")
        self.assertEqual(entry["guardrail_reason"], "category_not_allowed")
        self.assertIsNone(entry["order_id"])
        self.assertFalse(entry["capture_called"])

    def test_second_run_is_refused_while_gate_is_open(self):
        self.post("/api/run", {"job_id": "ATP-001"})
        self.wait_for(lambda s: s.get("status") == "awaiting_console",
                      "the gate to open")
        status, _ = self.post("/api/run", {"job_id": "ATP-002"})
        self.assertEqual(status, 409)
        self.post("/api/decide", {"decision": "deny"})
        self.wait_for(lambda s: s.get("status") == "done", "cleanup")


if __name__ == "__main__":
    unittest.main()
