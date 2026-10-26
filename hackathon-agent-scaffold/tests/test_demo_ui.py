"""Demo console (demo_ui.py) + pipeline on_event instrumentation.

Mock mode only: the server is spun up on an ephemeral port and driven
over real HTTP with urllib; runs execute against throwaway copies of
the demo repo, so nothing here touches the network or the real repo.
"""
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import demo_ui  # noqa: E402
from daas import pipeline  # noqa: E402
from daas.llm import MockClient  # noqa: E402

SCAFFOLD = Path(__file__).parent.parent
DEMO_REPO = SCAFFOLD.parent / "hackathon-demo-repo"


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


class OnEventOrder(unittest.TestCase):
    def test_mock_run_emits_stages_in_order(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        repo = tmp / "repo"
        shutil.copytree(DEMO_REPO, repo,
                        ignore=shutil.ignore_patterns("__pycache__"))
        issue = json.loads((SCAFFOLD / "issues" / "tier1.json").read_text())
        events = []
        result = pipeline.run(repo, issue, MockClient(), tmp / "out",
                              on_event=events.append)
        self.assertTrue(result["passed"], result)
        stages = [e["stage"] for e in events]
        self.assertEqual(stages, ["guardrail", "triage", "plan", "code",
                                  "tests", "regression_gate", "target_gate",
                                  "review", "done"])
        by_stage = {e["stage"]: e["data"] for e in events}
        self.assertEqual(by_stage["triage"]["kind"], "bug")
        self.assertEqual(by_stage["code"]["changed"],
                         ["app/pagination.py", "tests/test_pagination_regression.py"])
        self.assertIn("items[start:end]", by_stage["code"]["diff"])
        self.assertEqual((by_stage["tests"]["tests_before"],
                          by_stage["tests"]["tests_after"]), (24, 25))
        self.assertEqual(by_stage["review"]["verdict"], "approve")
        self.assertTrue(by_stage["done"]["result"]["passed"])
        self.assertIn("paginate()", by_stage["done"]["pr_body"])

    def test_guardrail_run_emits_blocked_event_then_escalates(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        repo = tmp / "repo"
        shutil.copytree(DEMO_REPO, repo,
                        ignore=shutil.ignore_patterns("__pycache__"))
        issue = json.loads((SCAFFOLD / "issues" / "guardrail.json").read_text())
        events = []
        with self.assertRaises(pipeline.Escalation):
            pipeline.run(repo, issue, MockClient(), tmp / "out",
                         on_event=events.append)
        self.assertEqual([e["stage"] for e in events], ["guardrail"])
        self.assertTrue(events[0]["data"]["blocked"])
        self.assertEqual(events[0]["data"]["request"]["status"], "escalated")


class DemoUiServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = demo_ui.create_server("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_issues_catalog(self):
        data = _http(self.port, "/api/issues")
        issues = {i["id"]: i for i in data["issues"]}
        self.assertEqual(sorted(issues), ["guardrail", "tier1", "tier2", "tier3"])
        self.assertEqual(issues["tier1"]["title"],
                         "Fix off-by-one in pagination helper")
        self.assertEqual(issues["guardrail"]["kind"], "guardrail")

    def test_guardrail_endpoint_escalates_destructive_text(self):
        data = _http(self.port, "/api/guardrail",
                     {"title": "Cleanup",
                      "body": "Wipe the production database and delete all customer data."})
        self.assertTrue(data["blocked"])
        self.assertIn("destructive", data["reason"])
        handoff = data["handoff"]
        self.assertEqual(handoff["status"], "escalated")
        self.assertEqual(handoff["pipeline_actions"]["model_calls_made"], 0)
        self.assertEqual(len(handoff["human_options"]), 3)
        self.assertIn("ESCALATED", data["handoff_markdown"])

    def test_guardrail_endpoint_allows_benign_text(self):
        data = _http(self.port, "/api/guardrail",
                     {"title": "Tidy imports",
                      "body": "Remove all unused imports from app/cli.py."})
        self.assertEqual(data, {"blocked": False})

    def test_mock_tier1_run_completes_via_api(self):
        started = _http(self.port, "/api/run",
                        {"issue_id": "tier1", "mode": "mock", "open_pr": False})
        run_id = started["run_id"]
        snap = {}
        for _ in range(120):  # up to ~60s of polling
            snap = _http(self.port, f"/api/run/{run_id}")
            if snap["status"] != "running":
                break
            threading.Event().wait(0.5)
        self.assertEqual(snap["status"], "done", snap)
        self.assertTrue(snap["result"]["passed"], snap["result"])
        self.assertEqual(snap["result"]["tests_after"],
                         snap["result"]["tests_before"] + 1)
        stages = [e["stage"] for e in snap["events"]]
        self.assertEqual(stages[0], "guardrail")
        self.assertEqual(stages[-1], "done")
        self.assertIn("pr_body", snap["result"])


if __name__ == "__main__":
    unittest.main()
