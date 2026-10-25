"""Pin the demo run-of-show (repo-root DEMO_RUN_OF_SHOW.md).

The run-of-show is a judged-demo artifact: it must drive the real
demo console, keep the pipeline stage order the console emits, stay
inside the script's 2:30-3:00 envelope, and point every fallback at
an artifact that actually exists in demo-fallbacks/.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "DEMO_RUN_OF_SHOW.md"


class TestDemoRunOfShow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_honest_not_recorded_status(self):
        self.assertIn("Not yet recorded", self.text)
        self.assertIn("No video exists yet", self.text)

    def test_drives_the_real_demo_console(self):
        for token in ("demo_ui.py", "--port 8765", "Try to break it",
                      "on_event", "125%"):
            self.assertIn(token, self.text, token)
        self.assertTrue(
            (ROOT / "hackathon-agent-scaffold" / "demo_ui.py").is_file())

    def test_stage_order_matches_pipeline_events(self):
        line = next(l for l in self.text.splitlines()
                    if l.strip().startswith("guardrail →"))
        stages = [s.strip() for s in line.split("→")]
        self.assertEqual(stages, ["guardrail", "triage", "plan", "code",
                                  "tests", "review", "done"])

    def test_timed_beats_inside_script_envelope(self):
        for token in ("0:00–0:25", "0:25–0:35", "0:35–1:35",
                      "1:35–2:00", "2:00–2:35", "2:35–3:00",
                      "2:30–3:00"):
            self.assertIn(token, self.text, token)

    def test_fallback_artifacts_exist(self):
        for rel in (
            "demo-fallbacks/live/tier1-pr16/pr_body.md",
            "demo-fallbacks/live/tier1-pr16/diff.patch",
            "demo-fallbacks/live/tier1-pr16/PROVENANCE.md",
            "demo-fallbacks/mock/tier1/result.json",
            "demo-fallbacks/mock/guardrail/escalation.md",
            "demo-fallbacks/mock/guardrail/approval_request.json",
            "demo-fallbacks/mock/manifest.json",
            "eval-scorecard/SCORECARD.md",
        ):
            self.assertIn(rel, self.text, rel)
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_two_takes_and_usable_definition(self):
        self.assertIn("Take 1 (primary)", self.text)
        self.assertIn("Take 2 (backup)", self.text)
        self.assertIn("no mock artifact is presented as live", self.text)

    def test_root_readme_links_it(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("DEMO_RUN_OF_SHOW.md", readme)


if __name__ == "__main__":
    unittest.main()
