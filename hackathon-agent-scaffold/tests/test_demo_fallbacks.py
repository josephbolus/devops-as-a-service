"""Demo fallback package completeness: recording day must never
depend on a live run, so every end state the demo script's fallbacks
point at is checked into demo-fallbacks/ and pinned here.

Mock artifacts must be what the generator produced (passed runs, no
unexpected files, a real diff, the escalation for the guardrail), and
the live artifact must be the captured PR #16 end state (a real Meta
API run), not a mock reconstruction.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
FALLBACKS = ROOT / "demo-fallbacks"
MOCK = FALLBACKS / "mock"
LIVE = FALLBACKS / "live" / "tier1-pr16"

EXPECTED_TESTS = {"tier1": (6, 7), "tier2": (6, 9), "tier3": (6, 8)}


class MockFallbacks(unittest.TestCase):
    def test_manifest_covers_all_four_issues(self):
        manifest = json.loads((MOCK / "manifest.json").read_text())
        self.assertEqual(manifest["mode"], "mock")
        runs = {r["slug"]: r for r in manifest["runs"]}
        self.assertEqual(sorted(runs), ["guardrail", "tier1", "tier2", "tier3"])
        self.assertTrue(runs["guardrail"]["escalated"])
        for slug in EXPECTED_TESTS:
            self.assertTrue(runs[slug]["passed"], slug)
            self.assertEqual(runs[slug]["unexpected_files"], [], slug)

    def test_each_tier_has_passing_pr_body_result_and_diff(self):
        for slug, (before, after) in EXPECTED_TESTS.items():
            with self.subTest(slug=slug):
                dest = MOCK / slug
                self.assertIn("All tests pass", (dest / "pr_body.md").read_text())
                result = json.loads((dest / "result.json").read_text())
                self.assertTrue(result["passed"])
                self.assertEqual((result["tests_before"], result["tests_after"]),
                                 (before, after))
                self.assertEqual(result["unexpected_files"], [])
                diff = (dest / "diff.patch").read_text()
                self.assertIn("--- a/", diff)
                for name in result["changed_unique"]:
                    self.assertIn(name, diff)

    def test_guardrail_fallback_is_an_escalation_not_a_pr(self):
        dest = MOCK / "guardrail"
        self.assertFalse((dest / "pr_body.md").exists())
        escalation = (dest / "escalation.md").read_text()
        self.assertIn("ESCALATED", escalation)
        self.assertIn("Human approval request", escalation)
        req = json.loads((dest / "approval_request.json").read_text())
        self.assertEqual(req["type"], "human_approval_request")
        self.assertEqual(req["pipeline_actions"]["model_calls_made"], 0)
        self.assertFalse(req["pipeline_actions"]["pr_opened"])
        result = json.loads((dest / "result.json").read_text())
        self.assertTrue(result["escalated"])
        self.assertFalse(result["passed"])


class LiveFallback(unittest.TestCase):
    def test_live_pr16_capture_is_present_and_real(self):
        meta = json.loads((LIVE / "pr.json").read_text())
        self.assertEqual(meta["number"], 16)
        self.assertEqual(meta["title"], "Fix off-by-one in pagination helper")
        self.assertIn("/pull/16", meta["url"])
        body = (LIVE / "pr_body.md").read_text()
        self.assertIn("All tests pass (6 → 8 discovered)", body)
        self.assertIn("approve:", body)
        diff = (LIVE / "diff.patch").read_text()
        self.assertIn("items[start:end]", diff)
        self.assertIn("test_pagination_regression", diff)
        self.assertIn("PR #16", (LIVE / "PROVENANCE.md").read_text())

    def test_readme_maps_fallbacks_and_labels_mock_vs_live(self):
        readme = (FALLBACKS / "README.md").read_text()
        self.assertIn("LIVE", readme)
        self.assertIn("MOCK", readme)
        self.assertIn("generate_demo_fallbacks.py", readme)


if __name__ == "__main__":
    unittest.main()
