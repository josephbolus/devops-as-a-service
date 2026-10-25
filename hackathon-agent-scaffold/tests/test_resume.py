"""Approve-and-resume (backlog item 3): a human decision on a guardrail
escalation must be validated, auditable, and - only for rescope -
resume the pipeline with a narrower issue that re-runs the guardrail.

Pins:
- record_decision validation and purity,
- reject / handle_manually close with ZERO model calls and no repo change,
- rescope resumes in mock mode and passes (Tier 1 rescoped issue),
- a still-destructive rescope re-escalates with zero model calls,
- resume with no decision raises,
- the demo console's /api/approval/decide wiring.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import demo_ui  # noqa: E402
from daas import approval, pipeline  # noqa: E402
from daas.llm import MockClient  # noqa: E402

SCAFFOLD = Path(__file__).parent.parent
DEMO_REPO = SCAFFOLD.parent / "hackathon-demo-repo"
AT = "2026-10-25T10:00:00-06:00"


def _issue(name):
    return json.loads((SCAFFOLD / "issues" / name).read_text())


def _escalated_request():
    return approval.build_request(_issue("guardrail.json"),
                                  "destructive operation on data")


class CountingClient(MockClient):
    def __init__(self):
        self.calls = 0

    def complete_json(self, system, user):
        self.calls += 1
        return super().complete_json(system, user)


def _copy_repo(tmp):
    repo = Path(tmp) / "repo"
    shutil.copytree(DEMO_REPO, repo,
                    ignore=shutil.ignore_patterns("__pycache__"))
    return repo


def _snapshot(repo):
    return {str(p.relative_to(repo)): p.read_bytes()
            for p in sorted(repo.rglob("*")) if p.is_file()}


class RecordDecision(unittest.TestCase):
    def test_rescope_records_and_does_not_mutate_input(self):
        req = _escalated_request()
        decided = approval.record_decision(
            req, "rescope", "Lead", AT, notes="do the safe part",
            rescoped_issue=_issue("tier1.json"))
        self.assertEqual(req["status"], "escalated")
        self.assertIsNone(req["decision_record"]["decision"])
        self.assertEqual(decided["status"], "approved_rescope")
        self.assertEqual(decided["decision_record"]["decision"], "rescope")
        self.assertEqual(decided["rescoped_issue"]["title"],
                         _issue("tier1.json")["title"])
        self.assertIn("Decision: rescope", approval.render_markdown(decided))

    def test_validation(self):
        req = _escalated_request()
        with self.assertRaises(ValueError):
            approval.record_decision(req, "approve_anyway", "Lead", AT)
        with self.assertRaises(ValueError):
            approval.record_decision(req, "reject", "", AT)
        with self.assertRaises(ValueError):
            approval.record_decision(req, "reject", "Lead", "")
        with self.assertRaises(ValueError):
            approval.record_decision(req, "rescope", "Lead", AT)
        with self.assertRaises(ValueError):
            approval.record_decision(req, "rescope", "Lead", AT,
                                     rescoped_issue={"body": "no title"})

    def test_reject_and_manual_statuses(self):
        req = _escalated_request()
        self.assertEqual(approval.record_decision(req, "reject", "L", AT)["status"],
                         "closed_rejected")
        self.assertEqual(approval.record_decision(req, "handle_manually", "L", AT)["status"],
                         "closed_manual")


class Resume(unittest.TestCase):
    def test_no_decision_raises_and_runs_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _copy_repo(tmp)
            client = CountingClient()
            with self.assertRaises(ValueError):
                pipeline.resume(repo, _escalated_request(), client, Path(tmp) / "out")
            self.assertEqual(client.calls, 0)

    def test_reject_closes_with_zero_calls_and_no_repo_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _copy_repo(tmp)
            before = _snapshot(repo)
            decided = approval.record_decision(_escalated_request(), "reject", "Lead", AT)
            client = CountingClient()
            out = pipeline.resume(repo, decided, client, Path(tmp) / "out")
            self.assertEqual(out["status"], "closed_rejected")
            self.assertFalse(out["resumed"])
            self.assertEqual(client.calls, 0)
            self.assertEqual(_snapshot(repo), before)
            saved = json.loads((Path(tmp) / "out" / "resume_result.json").read_text())
            self.assertEqual(saved["decision"], "reject")

    def test_handle_manually_closes_with_zero_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _copy_repo(tmp)
            decided = approval.record_decision(_escalated_request(),
                                               "handle_manually", "Lead", AT)
            client = CountingClient()
            out = pipeline.resume(repo, decided, client, Path(tmp) / "out")
            self.assertEqual(out["status"], "closed_manual")
            self.assertEqual(client.calls, 0)

    def test_rescope_resumes_mock_and_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _copy_repo(tmp)
            decided = approval.record_decision(
                _escalated_request(), "rescope", "Lead", AT,
                rescoped_issue=_issue("tier1.json"))
            events = []
            out = pipeline.resume(repo, decided, MockClient(), Path(tmp) / "out",
                                  on_event=events.append)
            self.assertTrue(out["resumed"])
            self.assertTrue(out["passed"], out)
            self.assertEqual(out["result"]["tests_before"], 6)
            self.assertGreater(out["result"]["tests_after"], 6)
            self.assertEqual(events[0]["stage"], "resume")
            self.assertIn("guardrail", [e["stage"] for e in events])
            saved = json.loads((Path(tmp) / "out" / "resume_result.json").read_text())
            self.assertEqual(saved["status"], "resumed")

    def test_still_destructive_rescope_re_escalates_with_zero_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _copy_repo(tmp)
            before = _snapshot(repo)
            decided = approval.record_decision(
                _escalated_request(), "rescope", "Lead", AT,
                rescoped_issue=_issue("guardrail.json"))
            client = CountingClient()
            with self.assertRaises(pipeline.Escalation):
                pipeline.resume(repo, decided, client, Path(tmp) / "out")
            self.assertEqual(client.calls, 0)
            self.assertEqual(_snapshot(repo), before)
            # a fresh approval request was written for the re-escalation
            req = json.loads((Path(tmp) / "out" / "approval_request.json").read_text())
            self.assertEqual(req["status"], "escalated")


class ResumeRunsRecord(unittest.TestCase):
    def test_committed_resume_runs_record(self):
        rec = json.loads((SCAFFOLD.parent / "eval-scorecard"
                          / "resume-runs.json").read_text())
        flows = {f["mode"]: f for f in rec["flows"]}
        self.assertEqual(sorted(flows), ["live", "mock"])
        for f in flows.values():
            self.assertTrue(f["escalated"], f)
            self.assertEqual(f["decision"], "rescope")
            self.assertTrue(f["passed"], f)
            self.assertGreater(f["tests_after"], f["tests_before"])
        self.assertEqual(flows["mock"]["tests_after"], 7)
        self.assertEqual(flows["live"]["role_models"]["CODER"], "muse-wonder-1.0")


class ConsoleWiring(unittest.TestCase):
    def test_decide_approval_helper(self):
        out = demo_ui.decide_approval(_escalated_request(), "rescope", "Op", AT,
                                      rescoped_issue=_issue("tier1.json"))
        self.assertTrue(out["will_resume"])
        self.assertEqual(out["request"]["decision_record"]["decision"], "rescope")
        out2 = demo_ui.decide_approval(_escalated_request(), "reject", "Op", AT)
        self.assertFalse(out2["will_resume"])
        with self.assertRaises(ValueError):
            demo_ui.decide_approval(_escalated_request(), "bogus", "Op", AT)


if __name__ == "__main__":
    unittest.main()
