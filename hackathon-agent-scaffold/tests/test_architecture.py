"""Pin the Day-8 architecture artifact (repo-root ARCHITECTURE.md).

The diagram is a judged artifact: it must name the real components in
this repo (not an aspirational design), keep the guardrail before any
model call, and carry the honest not-built-yet status.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCH = ROOT / "ARCHITECTURE.md"


class TestArchitectureDoc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = ARCH.read_text(encoding="utf-8")

    def test_mermaid_diagram_present(self):
        self.assertIn("```mermaid", self.text)
        self.assertIn("flowchart", self.text)

    def test_names_real_components(self):
        for token in (
            "daas/guardrail.py",
            "daas/approval.py",
            "daas/llm.py",
            "daas/pipeline.py",
            "daas/prompts.py",
            "run_pr.py",
            "run_resume.py",
            "run_scorecard.py",
            "generate_demo_fallbacks.py",
            "ConnectorClient",
            "MockClient",
            "muse-spark-1.3",
        ):
            self.assertIn(token, self.text, token)

    def test_named_files_actually_exist(self):
        scaffold = ROOT / "hackathon-agent-scaffold"
        for rel in (
            "daas/guardrail.py",
            "daas/approval.py",
            "daas/llm.py",
            "daas/pipeline.py",
            "daas/prompts.py",
            "run_pr.py",
            "run_resume.py",
            "run_scorecard.py",
            "generate_demo_fallbacks.py",
        ):
            self.assertTrue((scaffold / rel).is_file(), rel)

    def test_guardrail_runs_before_any_model_call(self):
        self.assertIn("before any model call", self.text)
        diagram = self.text.split("```mermaid", 1)[1].split("```", 1)[0]
        self.assertLess(diagram.index("guardrail"), diagram.index("Triage agent"))

    def test_honest_status_section(self):
        self.assertIn("What is not built yet", self.text)
        # approve-and-resume was a Days 5-6 gap; it is now recorded as
        # completed in the honest-status section, not claimed as a gap.
        self.assertIn("approve-and-resume flow", self.text)
        self.assertIn("completed", self.text)

    def test_root_readme_links_it(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("ARCHITECTURE.md", readme)


if __name__ == "__main__":
    unittest.main()
