"""Judge Mode for the demo console (demo_ui judge plumbing).

Pins: a caption exists for every pipeline stage and is derived from the
event that fired; a one-click judge run completes over real HTTP in mock
mode with captions, per-stage timings, and a closing results card whose
pass/fail, test delta, and links match the run's actual record.
"""
import json
import sys
import threading
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import demo_ui  # noqa: E402


def _http(port, path, payload=None):
    url = f"http://127.0.0.1:{port}{path}"
    if payload is None:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read())
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _poll(port, run_id):
    snap = {}
    for _ in range(120):
        snap = _http(port, f"/api/run/{run_id}")
        if snap["status"] != "running":
            return snap
        threading.Event().wait(0.5)
    return snap


class Captions(unittest.TestCase):
    EVENTS = [
        {"stage": "guardrail", "data": {"blocked": False}},
        {"stage": "guardrail", "data": {"blocked": True, "reason": "destructive"}},
        {"stage": "triage", "data": {"kind": "bug"}},
        {"stage": "plan", "data": {"steps": ["a", "b"]}},
        {"stage": "code", "data": {"changed": ["app/x.py"]}},
        {"stage": "tests", "data": {"tests_ok": True, "tests_before": 6, "tests_after": 7}},
        {"stage": "tests", "data": {"tests_ok": False, "tests_before": 6, "tests_after": 6}},
        {"stage": "review", "data": {"verdict": "approve"}},
        {"stage": "done", "data": {"result": {"passed": True}}},
        {"stage": "done", "data": {"result": {"passed": False}}},
    ]

    def test_every_stage_has_a_judge_caption(self):
        for ev in self.EVENTS:
            cap = demo_ui.caption_for_event(ev)
            self.assertTrue(cap.startswith("Judge Mode:"), (ev, cap))
            self.assertGreater(len(cap), 40, (ev, cap))

    def test_captions_are_derived_from_the_event(self):
        cap = demo_ui.caption_for_event(
            {"stage": "tests", "data": {"tests_ok": True, "tests_before": 6, "tests_after": 9}})
        self.assertIn("6 → 9", cap)
        self.assertIn("+3", cap)
        blocked = demo_ui.caption_for_event(self.EVENTS[1])
        self.assertIn("before any model ran", blocked)


class ResultsCard(unittest.TestCase):
    def _snap(self, **over):
        snap = {"status": "done", "result": {"passed": True, "tests_before": 6, "tests_after": 7},
                "events": [
                    {"stage": "guardrail", "data": {"blocked": False}, "elapsed_ms": 1},
                    {"stage": "triage", "data": {"kind": "bug"}, "elapsed_ms": 2},
                    {"stage": "plan", "data": {"steps": ["s"]}, "elapsed_ms": 3},
                    {"stage": "code", "data": {"changed": ["a"]}, "elapsed_ms": 4},
                    {"stage": "tests", "data": {"tests_ok": True, "tests_before": 6, "tests_after": 7}, "elapsed_ms": 5},
                    {"stage": "review", "data": {"verdict": "approve"}, "elapsed_ms": 6},
                    {"stage": "done", "data": {"result": {"passed": True}}, "elapsed_ms": 7},
                ]}
        snap.update(over)
        return snap

    def test_passing_card(self):
        card = demo_ui.results_card(self._snap())
        self.assertEqual(card["overall"], "pass")
        self.assertEqual([s["status"] for s in card["stages"]], ["pass"] * 7)
        self.assertEqual([s["stage"] for s in card["stages"]], demo_ui.JUDGE_STAGES)
        self.assertEqual(card["tests_delta"], 1)
        self.assertEqual(card["total_elapsed_ms"], 7)
        self.assertIn("/pull/16", card["links"]["live_prs"][0])
        self.assertIn("eval-scorecard/SCORECARD.md", card["links"]["eval_scorecard"])

    def test_failing_tests_stage_is_named(self):
        snap = self._snap(result={"passed": False, "tests_before": 6, "tests_after": 6})
        snap["events"][4]["data"] = {"tests_ok": False, "tests_before": 6, "tests_after": 6}
        snap["events"][6]["data"] = {"result": {"passed": False}}
        card = demo_ui.results_card(snap)
        by = {s["stage"]: s["status"] for s in card["stages"]}
        self.assertEqual(by["tests"], "fail")
        self.assertEqual(by["done"], "fail")
        self.assertEqual(card["overall"], "fail")

    def test_escalated_card(self):
        snap = {"status": "escalated", "result": None, "events": [
            {"stage": "guardrail", "data": {"blocked": True, "reason": "destructive"}, "elapsed_ms": 1}]}
        card = demo_ui.results_card(snap)
        self.assertEqual(card["overall"], "escalated")
        self.assertEqual(card["stages"][0]["status"], "escalated")
        self.assertEqual(card["stages"][1]["status"], "pending")

    def test_page_contains_judge_mode(self):
        self.assertIn("judgeBtn", demo_ui.PAGE)
        self.assertIn("/api/judge/run", demo_ui.PAGE)
        self.assertIn("judgeResults", demo_ui.PAGE)
        self.assertIn("judgeCaption", demo_ui.PAGE)


class JudgeRunOverHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = demo_ui.create_server("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_one_click_judge_run_completes_with_card(self):
        started = _http(self.port, "/api/judge/run", {})
        self.assertTrue(started["judge_mode"])
        snap = _poll(self.port, started["run_id"])
        self.assertEqual(snap["status"], "done", snap)
        self.assertTrue(snap["judge_mode"])
        # Events include the deterministic regression_gate stage
        # (iteration 26) between tests and review; the results card
        # still summarises the seven JUDGE_STAGES.
        self.assertEqual([e["stage"] for e in snap["events"]],
                         ["guardrail", "triage", "plan", "code", "tests",
                          "regression_gate", "review", "done"])
        # Captions + timings travel with each event.
        for e in snap["events"]:
            self.assertTrue(e["caption"].startswith("Judge Mode:"), e)
            self.assertIsInstance(e["elapsed_ms"], int)
        self.assertEqual(snap["captions"], [e["caption"] for e in snap["events"]])
        card = snap["results_card"]
        self.assertEqual(card["overall"], "pass")
        self.assertEqual(card["tests_delta"], 1)
        self.assertTrue(all(s["status"] == "pass" for s in card["stages"]))
        self.assertEqual(len(card["links"]["live_prs"]), 3)

    def test_judge_guardrail_run_ends_escalated(self):
        started = _http(self.port, "/api/judge/run", {"issue_id": "guardrail", "mode": "mock"})
        snap = _poll(self.port, started["run_id"])
        self.assertEqual(snap["status"], "escalated", snap)
        self.assertEqual(snap["results_card"]["overall"], "escalated")
        self.assertIn("before any model ran", snap["events"][0]["caption"])


if __name__ == "__main__":
    unittest.main()
