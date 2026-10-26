"""Plan gate (maximizer iteration 24).

Pins the deterministic gate added after the negative-controls eval
measured a false pass on a non-existent target: for a bug report, a
plan naming a non-test production file that does not exist in the
repo escalates BEFORE the coder runs. Feature requests are exempt
(creating a module can be the work); new test files are exempt.
"""
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
TREE = ["app/pagination.py", "app/cli.py", "tests/test_baseline.py"]


class TestInventedProductionFiles(unittest.TestCase):
    def test_bug_with_only_existing_and_new_test_files(self):
        plan = {"expected_files": ["app/pagination.py",
                                   "tests/test_new_regression.py"]}
        self.assertEqual(
            pipeline.invented_production_files(plan, TREE, {"kind": "bug"}),
            [])

    def test_bug_with_invented_production_file(self):
        plan = {"expected_files": ["app/statistics.py",
                                   "tests/test_statistics_regression.py"]}
        self.assertEqual(
            pipeline.invented_production_files(plan, TREE, {"kind": "bug"}),
            ["app/statistics.py"])

    def test_feature_is_exempt(self):
        plan = {"expected_files": ["app/statistics.py"]}
        self.assertEqual(
            pipeline.invented_production_files(plan, TREE, {"kind": "feature"}),
            [])

    def test_chore_is_exempt(self):
        plan = {"expected_files": ["app/statistics.py"]}
        self.assertEqual(
            pipeline.invented_production_files(plan, TREE, {"kind": "chore"}),
            [])


class InventingClient(MockClient):
    """Triage/planner invent a production file; coder must never run."""

    def __init__(self, kind):
        self.kind = kind
        self.coder_calls = 0

    def complete_json(self, system, user):
        role = system.strip().split()[0].upper()
        if role == "TRIAGE":
            return {"kind": self.kind, "summary": "s", "acceptance": ["a"]}
        if role == "PLANNER":
            return {"steps": ["fix it"],
                    "expected_files": ["app/invented_module.py",
                                       "tests/test_invented_regression.py"]}
        if role == "CODER":
            self.coder_calls += 1
            return {"edits": [
                {"file": "app/invented_module.py", "old": None,
                 "new": "VALUE = 1\n"},
                {"file": "tests/test_invented_regression.py", "old": None,
                 "new": ("import unittest\n\nfrom app.invented_module "
                         "import VALUE\n\n\nclass T(unittest.TestCase):\n"
                         "    def test_value(self):\n"
                         "        self.assertEqual(VALUE, 1)\n")}]}
        if role == "REVIEWER":
            return {"verdict": "approve", "notes": "ok"}
        raise AssertionError(role)


class TestPlanGateEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        shutil.copytree(DEMO_REPO, self.repo,
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.out = self.tmp / "out"
        self.issue = {"title": "Fix the invented module",
                      "body": "It is broken."}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_bug_plan_inventing_a_file_escalates_before_the_coder(self):
        client = InventingClient("bug")
        with self.assertRaises(pipeline.Escalation) as ctx:
            pipeline.run(self.repo, self.issue, client, self.out)
        self.assertIn("app/invented_module.py", ctx.exception.reason)
        self.assertEqual(client.coder_calls, 0)
        self.assertFalse((self.repo / "app" / "invented_module.py").exists())
        self.assertTrue((self.out / "escalation.md").exists())

    def test_feature_plan_may_create_the_module(self):
        client = InventingClient("feature")
        result = pipeline.run(self.repo, self.issue, client, self.out)
        self.assertTrue(result["passed"], result)
        self.assertTrue((self.repo / "app" / "invented_module.py").exists())


if __name__ == "__main__":
    unittest.main()
