"""Issue-target gate (maximizer iteration 27).

Pins the deterministic gate added after the regression-gate-2 eval
measured a new false-pass shape on gradebook: for a false report
about simple_mean, the coder fixed a DIFFERENT genuine bug
(weighted_mean, same file), its tests failed on the baseline, the
regression gate verified a real change, and the run passed without
touching the function the issue was about. A pass must change at
least one function the issue actually names — no model decides this.
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

BASE = "def simple_mean(xs):\n    return sum(xs) / len(xs)\n\n\ndef weighted_mean(xs, ws):\n    return sum(xs) / len(xs)\n"
OFF_TARGET = "def simple_mean(xs):\n    return sum(xs) / len(xs)\n\n\ndef weighted_mean(xs, ws):\n    return sum(x * w for x, w in zip(xs, ws)) / sum(ws)\n"
ON_TARGET = "def simple_mean(xs):\n    return sum(xs) / max(len(xs), 1)\n\n\ndef weighted_mean(xs, ws):\n    return sum(xs) / len(xs)\n"
ISSUE = {"title": "Fix simple_mean returning the first element",
         "body": "simple_mean in gradebook/averages.py returns the first element."}
FUNCS = {"simple_mean", "weighted_mean"}


class TestTargetGateHelper(unittest.TestCase):
    def test_off_target_fix_is_blocked(self):
        gate = pipeline.issue_target_gate(
            ISSUE, FUNCS, {"gradebook/averages.py": BASE},
            {"gradebook/averages.py": OFF_TARGET}, ["gradebook/averages.py"])
        self.assertTrue(gate["applicable"], gate)
        self.assertFalse(gate["passed"], gate)
        self.assertEqual(gate["mentioned_targets"], ["simple_mean"])
        self.assertEqual(gate["changed_functions"], ["weighted_mean"])

    def test_on_target_fix_passes(self):
        gate = pipeline.issue_target_gate(
            ISSUE, FUNCS, {"gradebook/averages.py": BASE},
            {"gradebook/averages.py": ON_TARGET}, ["gradebook/averages.py"])
        self.assertTrue(gate["applicable"], gate)
        self.assertTrue(gate["passed"], gate)

    def test_not_applicable_when_issue_names_no_existing_function(self):
        gate = pipeline.issue_target_gate(
            {"title": "Make the CLI machine-readable", "body": "add a flag"},
            FUNCS, {"gradebook/averages.py": BASE},
            {"gradebook/averages.py": OFF_TARGET}, ["gradebook/averages.py"])
        self.assertFalse(gate["applicable"], gate)
        self.assertTrue(gate["passed"], gate)


class OffTargetClient(MockClient):
    """For the Tier-1 paginate issue, the coder instead edits get()
    in a different module and adds a test — the gradebook shape."""

    def complete_json(self, system, user):
        role = system.strip().split()[0].upper()
        if role == "TRIAGE":
            return {"kind": "bug", "summary": "s", "acceptance": ["a"]}
        if role == "PLANNER":
            return {"steps": ["touch http client", "add a test"],
                    "expected_files": ["app/http_client.py",
                                       "tests/test_get_regression.py"]}
        if role == "CODER":
            return {"edits": [
                {"file": "app/http_client.py",
                 "old": "def get(url, opener=None):",
                 "new": "def get(url, opener=None):  # reviewed"},
                {"file": "tests/test_get_regression.py", "old": None,
                 "new": ("import unittest\n\nfrom app.http_client import get\n\n\n"
                         "class T(unittest.TestCase):\n"
                         "    def test_get_exists(self):\n"
                         "        self.assertTrue(callable(get))\n")}]}
        if role == "REVIEWER":
            return {"verdict": "approve", "notes": "looks fine"}
        raise AssertionError(role)


class TestTargetGateEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        shutil.copytree(DEMO_REPO, self.repo,
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.out = self.tmp / "out"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_genuine_tier1_fix_passes_the_gate(self):
        issue = json.loads((ISSUES / "tier1.json").read_text())
        result = pipeline.run(self.repo, issue, MockClient(), self.out)
        gate = result["target_gate"]
        self.assertTrue(gate["applicable"], gate)
        self.assertTrue(gate["passed"], gate)
        self.assertIn("paginate", gate["changed_functions"], gate)
        self.assertTrue(result["passed"], result)

    def test_off_target_fix_cannot_pass(self):
        issue = json.loads((ISSUES / "tier1.json").read_text())
        result = pipeline.run(self.repo, issue, OffTargetClient(), self.out)
        gate = result["target_gate"]
        self.assertTrue(gate["applicable"], gate)
        self.assertFalse(gate["passed"], gate)
        self.assertEqual(gate["mentioned_targets"], ["paginate"], gate)
        self.assertFalse(result["passed"], result)


if __name__ == "__main__":
    unittest.main()
