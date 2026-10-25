## Add a --json flag to app/cli.py to emit the same REPORT data from app/report.py as a single JSON document while keeping human output as the unchanged default

Closes: Make the CLI output machine-readable

### Plan
- Inspect app/cli.py and app/report.py to confirm REPORT dict shape and current human output
- Add --json flag to app/cli.py to emit REPORT service/status/checks with name/ok/latency_ms as single JSON document on stdout, leaving default human path unchanged
- Add regression test verifying --json parses and matches REPORT and default output is unchanged
- Run existing tests to confirm no regressions

### Files changed
- app/cli.py
- tests/test_cli_regression.py

### Tests
All tests pass (6 → 8 discovered).

### Reviewer
approve: Checked app/cli.py --json implementation and tests/test_cli_regression.py; no unrelated changes; tests 6->8 pass; regression tests cover default human output and --json parsing matching REPORT; no missing test or risk.

