"""Pin the Day-8 submission dry-run package (repo-root SUBMISSION.md + LICENSE).

The sprint plan's Day-8 exit criteria are: README polish, architecture
diagram, scorecard, how to run, license file, draft submission text,
and repo hygiene (no secrets, no stray branches claimed falsely).
This test pins the loop-producible parts: the license, the draft's
required sections and measured numbers, and its honest status —
draft, not submitted; video not yet recorded.
"""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUBMISSION = ROOT / "SUBMISSION.md"
LICENSE = ROOT / "LICENSE"


class TestLicense(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = LICENSE.read_text(encoding="utf-8")

    def test_mit_license_present(self):
        self.assertIn("MIT License", self.text)
        self.assertIn("Copyright (c) 2026 Joseph Bolus", self.text)
        self.assertIn("Permission is hereby granted", self.text)


class TestSubmissionDraft(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SUBMISSION.read_text(encoding="utf-8")

    def test_honest_status_not_submitted(self):
        self.assertIn("not submitted", self.text)
        self.assertIn("Nov 4, 2026, 9:00 PM ET", self.text)

    def test_video_gap_is_a_placeholder_not_a_claim(self):
        self.assertIn("not yet recorded", self.text)
        self.assertIn("no video exists yet", self.text)
        self.assertIn("TO BE ADDED", self.text)

    def test_form_fields_present(self):
        for token in (
            "DevOps as a Service",
            "Indie Dev Track",
            "https://github.com/josephbolus/devops-as-a-service",
        ):
            self.assertIn(token, self.text, token)

    def test_criteria_sections_present(self):
        for token in ("Impact — 30%", "Meta AI Tooling — 25%", "Demo (25%)",
                      "Technical depth & execution (20%)"):
            self.assertIn(token, self.text, token)

    def test_measured_numbers_match_the_records(self):
        # Numbers copied from eval-scorecard records; if a record is
        # re-measured, this draft must be updated in the same commit.
        for token in ("3/3", "94.65s", "6 → 9", "6 → 10", "6 → 8",
                      "#16", "#17", "#18", "50 min saved",
                      "216.7", "+10 vs +9", "209.14s", "16.84s",
                      "156/156"):
            self.assertIn(token, self.text, token)

    def test_current_evidence_included(self):
        # Iteration 18: the draft must carry the post-dry-run measured
        # record, not the stale Day-8 snapshot.
        for token in ("9/9", "9 → 13", "10 → 15", "$0.0254", "Judge Mode",
                      "JUDGE_TOUR.md", "GENERALIZATION.md", "GENERALIZATION2.md"):
            self.assertIn(token, self.text, token)
        self.assertNotIn("one run each", self.text)

    def test_models_named(self):
        self.assertIn("muse-wonder-1.0", self.text)
        self.assertIn("muse-spark-1.3", self.text)

    def test_dry_run_checklist_present(self):
        self.assertIn("Dry-run checklist", self.text)
        self.assertIn("LICENSE", self.text)

    def test_root_readme_links_both(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("SUBMISSION.md", readme)
        self.assertIn("LICENSE", readme)


class TestRepoHygiene(unittest.TestCase):
    def test_no_tracked_file_contains_a_key_value(self):
        # Env-var NAMES are fine; a key VALUE (long sk-/key-like token
        # assigned in a tracked file) is not. Scan tracked files only.
        out = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
            check=True).stdout.splitlines()
        pattern = re.compile(r"(MODEL_API_KEY|META_API_KEY)\s*=\s*['\"]?[A-Za-z0-9_\-]{20,}")
        offenders = []
        for rel in out:
            path = ROOT / rel
            if path.is_file() and path.suffix in (".py", ".md", ".json", ".txt"):
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if pattern.search(line) and "dummy" not in line:
                        offenders.append(f"{rel}: {line.strip()[:60]}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
