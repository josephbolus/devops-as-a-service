import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from daas import pipeline  # noqa: E402
from daas.llm import MockClient  # noqa: E402

DEMO_REPO = Path(__file__).parent.parent.parent / "hackathon-demo-repo"


class PipelineEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        shutil.copytree(DEMO_REPO, self.repo,
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.out = self.tmp / "out"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tier1_goes_in_fix_comes_out(self):
        issue = json.loads((Path(__file__).parent.parent / "issues" / "tier1.json").read_text())
        result = pipeline.run(self.repo, issue, MockClient(), self.out)
        self.assertTrue(result["tests_ok"], result["test_log_tail"])
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["unexpected_files"], [])
        # The bug is actually fixed in the copy:
        sys.path.insert(0, str(self.repo))
        from app.pagination import paginate
        self.assertEqual(len(paginate(list(range(20)), 2, 10)), 10)
        self.assertIn("All tests pass", (self.out / "pr_body.md").read_text())

    def _run_issue(self, name):
        issue = json.loads((Path(__file__).parent.parent / "issues" / name).read_text())
        return pipeline.run(self.repo, issue, MockClient(), self.out)

    def test_tier2_retry_comes_out(self):
        result = self._run_issue("tier2.json")
        self.assertTrue(result["tests_ok"], result["test_log_tail"])
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["unexpected_files"], [])
        self.assertEqual(sorted(set(result["changed"])),
                         ["app/http_client.py", "tests/test_http_retry.py"])
        text = (self.repo / "app" / "http_client.py").read_text()
        self.assertIn("max_retries=3", text)
        self.assertIn("backoff_base", text)

    def test_tier3_json_flag_comes_out(self):
        result = self._run_issue("tier3.json")
        self.assertTrue(result["tests_ok"], result["test_log_tail"])
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["unexpected_files"], [])
        self.assertEqual(sorted(set(result["changed"])),
                         ["app/cli.py", "app/report.py", "tests/test_cli_json.py"])
        self.assertIn("--json", (self.repo / "app" / "cli.py").read_text())

    def test_guardrail_escalates_and_touches_nothing(self):
        before = (self.repo / "app" / "pagination.py").read_text()
        issue = json.loads((Path(__file__).parent.parent / "issues" / "guardrail.json").read_text())
        with self.assertRaises(pipeline.Escalation):
            pipeline.run(self.repo, issue, MockClient(), self.out)
        self.assertEqual(before, (self.repo / "app" / "pagination.py").read_text())
        self.assertTrue((self.out / "escalation.md").exists())


if __name__ == "__main__":
    unittest.main()
