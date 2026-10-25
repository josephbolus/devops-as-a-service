"""Human-approval handoff: a guardrail escalation must produce a
structured, auditable approval request - not just a refusal note.

Added Oct 25 (maximizer iteration 5) as a loop-sized slice of the
Days 5-6 human-approval gate. Pins: the machine-readable request
(recording that the pipeline provably did nothing), the walkable
markdown form used as the demo's trust beat, and the pipeline wiring
that writes both artifacts on escalation.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from daas import approval, pipeline  # noqa: E402
from daas.llm import MockClient  # noqa: E402

ISSUE = {"title": "Delete the legacy database and drop old tables",
         "body": "Clean up: delete the legacy database and drop old tables."}
REASON = "destructive operation on data"
DEMO_REPO = Path(__file__).parent.parent.parent / "hackathon-demo-repo"


class ApprovalRequest(unittest.TestCase):
    def test_request_records_that_pipeline_did_nothing(self):
        req = approval.build_request(ISSUE, REASON)
        self.assertEqual(req["type"], "human_approval_request")
        self.assertEqual(req["status"], "escalated")
        self.assertEqual(req["issue_title"], ISSUE["title"])
        self.assertEqual(req["guardrail_reason"], REASON)
        actions = req["pipeline_actions"]
        self.assertEqual(actions["model_calls_made"], 0)
        self.assertEqual(actions["agents_ran"], [])
        self.assertEqual(actions["files_changed"], [])
        self.assertFalse(actions["pr_opened"])

    def test_request_offers_three_real_decisions_and_a_blank_record(self):
        req = approval.build_request(ISSUE, REASON)
        self.assertEqual([o["id"] for o in req["human_options"]],
                         ["reject", "rescope", "handle_manually"])
        for opt in req["human_options"]:
            self.assertTrue(opt["label"])
            self.assertTrue(opt["effect"])
        record = req["decision_record"]
        self.assertEqual(sorted(record),
                         ["decided_at", "decided_by", "decision", "notes"])
        self.assertTrue(all(v is None for v in record.values()))

    def test_markdown_is_walkable_and_keeps_the_escalation_contract(self):
        md = approval.render_markdown(approval.build_request(ISSUE, REASON))
        self.assertIn("ESCALATED", md)
        self.assertIn(ISSUE["title"], md)
        self.assertIn(REASON, md)
        self.assertIn("What the pipeline did NOT do", md)
        self.assertIn("Model calls made: 0", md)
        self.assertIn("Pull request opened: no", md)
        self.assertIn("Decision record", md)
        for opt in approval.OPTIONS:
            self.assertIn(opt["label"], md)

    def test_json_round_trips(self):
        req = approval.build_request(ISSUE, REASON)
        self.assertEqual(json.loads(approval.to_json(req)), req)


class PipelineWiring(unittest.TestCase):
    def test_escalation_writes_both_artifacts_and_touches_nothing(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            repo = tmp / "repo"
            shutil.copytree(DEMO_REPO, repo,
                            ignore=shutil.ignore_patterns("__pycache__"))
            before = {str(p.relative_to(repo)): p.read_bytes()
                      for p in sorted(repo.rglob("*")) if p.is_file()}
            out = tmp / "out"
            issue = json.loads((Path(__file__).parent.parent
                                / "issues" / "guardrail.json").read_text())
            with self.assertRaises(pipeline.Escalation):
                pipeline.run(repo, issue, MockClient(), out)
            after = {str(p.relative_to(repo)): p.read_bytes()
                     for p in sorted(repo.rglob("*")) if p.is_file()}
            self.assertEqual(before, after)
            self.assertIn("ESCALATED", (out / "escalation.md").read_text())
            req = json.loads((out / "approval_request.json").read_text())
            self.assertEqual(req["issue_title"], issue["title"])
            self.assertEqual(req["pipeline_actions"]["model_calls_made"], 0)
            self.assertFalse(req["pipeline_actions"]["pr_opened"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
