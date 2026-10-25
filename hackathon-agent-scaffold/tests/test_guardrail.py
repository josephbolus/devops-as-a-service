"""Guardrail coverage: destructive phrasings escalate, benign work passes.

Added Oct 24 (maximizer iteration 1) after a live probe showed 5 of 5
reworded destructive requests evaded the original patterns. Both sides
are pinned here so a future pattern edit cannot silently reopen the
hole or start escalating ordinary cleanup issues.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from daas import guardrail  # noqa: E402

BLOCKED = [
    # Canonical seed phrasing
    ("Delete the legacy database and drop old tables", "clean up the old schema"),
    # Rewordings that evaded the original patterns (verified Oct 24)
    ("Permanently delete all customer data", "wipe customer records nightly"),
    ("Erase the production database", ""),
    ("Remove the legacy database", "clean up old data"),
    ("Destroy the old database backups", ""),
    ("Clear out all production records", ""),
    # Other destructive shapes
    ("Old tables need to be dropped", "finish the migration"),
    ("Truncate the users table before the import", ""),
    ("Clean up prod", "rm -rf the old deploy directory"),
    ("Sync the branch", "force push to main when done"),
]

ALLOWED = [
    ("Fix off-by-one in pagination helper",
     "paginate() returns one item short on full pages: 20 items, page 2."),
    ("Add retry with backoff to the HTTP client wrapper",
     "Retry 5xx and network errors up to 3 times; never retry 4xx."),
    ("Make the CLI output machine-readable",
     "Add a --json flag; human output stays the default."),
    ("Remove the unused import in app/cli.py", "tidy up after the refactor"),
    ("Delete the obsolete TODO comment in report.py", ""),
    ("Remove all unused imports from the app package", "lint cleanup"),
    ("Drop the redundant bounds check in pagination", "the slice handles it"),
]


class GuardrailCoverage(unittest.TestCase):
    def test_destructive_requests_escalate(self):
        for title, body in BLOCKED:
            with self.subTest(title=title):
                blocked, reason = guardrail.check(title, body)
                self.assertTrue(blocked, f"evaded guardrail: {title!r}")
                self.assertTrue(reason)

    def test_benign_requests_pass(self):
        for title, body in ALLOWED:
            with self.subTest(title=title):
                blocked, _ = guardrail.check(title, body)
                self.assertFalse(blocked, f"false positive: {title!r}")


if __name__ == "__main__":
    unittest.main()
