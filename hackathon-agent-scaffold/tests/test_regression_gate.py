"""Regression gate (maximizer iteration 26).

Pins the deterministic gate added after iterations 24-25 measured
that false bug reports were stopped only by the reviewer: a run's
new tests must FAIL on the baseline production code, or the run
cannot pass — no model call decides this.
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
ISSUES = Path(__file__).parent.parent / "issues"


class NoOpFixClient(MockClient):
    """Coder makes a behaviour-preserving edit and adds a test that
    already passes on the baseline; reviewer approves. Only the
    regression gate can stop this run."""

    def complete_json(self, system, user):
        role = system.strip().split()[0].upper()
        if role == "TRIAGE":
            return {"kind": "bug", "summary": "s", "acceptance": ["a"]}
        if role == "PLANNER":
            return {"steps": ["touch pagination", "add a test"],
                    "expected_files": ["app/pagination.py",
                                       "tests/test_noop_regression.py"]}
        if role == "CODER":
            return {"edits": [
                {"file": "app/pagination.py",
                 "old": "def paginate(items, page, page_size):",
                 "new": "def paginate(items, page, page_size):  # reviewed"},
                {"file": "tests/test_noop_regression.py", "old": None,
                 "new": ("import unittest\n\nfrom app.pagination import "
                         "paginate\n\n\nclass T(unittest.TestCase):\n"
                         "    def test_partial_page(self):\n"
                         "        self.assertEqual(paginate(list(range(3)), 1, 10), "
                         "list(range(3)))\n")}]}
        if role == "REVIEWER":
            return {"verdict": "approve", "notes": "looks fine"}
        raise AssertionError(role)


class TestRegressionGateEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        shutil.copytree(DEMO_REPO, self.repo,
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.out = self.tmp / "out"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_genuine_fix_passes_the_gate(self):
        issue = json.loads((ISSUES / "tier1.json").read_text())
        result = pipeline.run(self.repo, issue, MockClient(), self.out)
        gate = result["regression_gate"]
        self.assertTrue(gate["applicable"], gate)
        self.assertTrue(gate["passed"], gate)
        self.assertFalse(gate["tests_ok_on_baseline"], gate)
        self.assertTrue(result["passed"], result)
        # The fix is restored after the gate ran:
        self.assertIn("return items[start:end]",
                      (self.repo / "app" / "pagination.py").read_text())

    def test_noop_fix_with_baseline_passing_test_is_blocked(self):
        issue = {"title": "Fix paginate (no-op)", "body": "claimed bug"}
        result = pipeline.run(self.repo, issue, NoOpFixClient(), self.out)
        gate = result["regression_gate"]
        self.assertTrue(gate["applicable"], gate)
        self.assertFalse(gate["passed"], gate)
        self.assertTrue(gate["tests_ok_on_baseline"], gate)
        self.assertTrue(result["tests_ok"], result)
        self.assertFalse(result["passed"], result)

    def test_gate_not_applicable_without_test_change(self):
        gate = pipeline.regression_gate(
            self.repo, {"app/x.py": "a"}, {"app/x.py": "b"}, ["app/x.py"])
        self.assertFalse(gate["applicable"])
        self.assertTrue(gate["passed"])


if __name__ == "__main__":
    unittest.main()
