## CLI prints only the human report; scripts cannot consume it

Closes: Make the CLI output machine-readable

### Plan
- Add json_report() to app/report.py returning the REPORT dict as JSON
- Branch on --json in app/cli.py main(); human output stays default
- Add tests that --json parses and matches REPORT, and default output is unchanged

### Files changed
- app/report.py
- app/cli.py
- app/cli.py
- tests/test_cli_json.py

### Tests
All tests pass (24 → 26 discovered).

### Regression gate
Verified: suite fails on baseline production code, so the new tests demonstrate the claimed change.

### Issue-target gate
Not applicable: issue names no existing function, or no production code changed — nothing to verify the target against.

### Reviewer
approve: Diff limited to expected files; regression test added.
