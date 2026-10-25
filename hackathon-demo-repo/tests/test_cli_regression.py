"""Regression tests for --json flag."""

import contextlib
import io
import json
import unittest

from app import cli
from app.report import REPORT, human_report


def _capture_main(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(argv)
    return rc, buf.getvalue()


class TestCliJsonRegression(unittest.TestCase):
    def test_default_output_is_human_report(self):
        rc, out = _capture_main([])
        self.assertEqual(rc, 0)
        self.assertEqual(out, human_report() + "\n")

    def test_json_output_parses_and_matches_report(self):
        rc, out = _capture_main(["--json"])
        self.assertEqual(rc, 0)
        parsed = json.loads(out)
        self.assertEqual(parsed, REPORT)
        self.assertEqual(parsed["service"], REPORT["service"])
        self.assertEqual(parsed["status"], REPORT["status"])
        self.assertEqual(len(parsed["checks"]), len(REPORT["checks"]))
        for actual, expected in zip(parsed["checks"], REPORT["checks"]):
            self.assertEqual(actual["name"], expected["name"])
            self.assertEqual(actual["ok"], expected["ok"])
            self.assertEqual(actual["latency_ms"], expected["latency_ms"])


if __name__ == "__main__":
    unittest.main()
