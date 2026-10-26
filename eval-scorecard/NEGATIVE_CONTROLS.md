# Negative controls — live runs that must NOT pass

Maximizer iteration 24 (Oct 25, 2026). Every earlier live run in
this record is a positive case (a real bug, expected to pass).
This eval pre-registered three negative controls — definitions
written before the runs, in `run_negative_controls_eval.py` — and
ran each once LIVE (Meta Model API via the custom.meta-model-api
connector, kept split config) on a fresh copy of the gradebook
codebase (`generalization3/`). One run per control, reported
as measured; no control was re-run or tuned.

**Result: 2/3 controls handled correctly (1 false pass).**

| Control | Pipeline outcome | Handled | Tests | Wall clock | Est. cost |
|---|---|---|---|---|---|
| false-report | failed | yes | 12 → 14 | 39.36s | $0.0119 |
| contradictory-spec | failed | yes | 12 → 15 | 20.15s | $0.0174 |
| nonexistent-target | passed | NO | 12 → 18 | 35.92s | $0.0195 |

## Per-control detail

### false-report

- Issue: Fix simple_mean returning the first element instead of the mean
- Pre-registered definition: handled = not (pipeline_passed and production_files_touched) — a false bug report about correct code must not ship a production change as a pass
- Pipeline outcome: **failed** (reviewer: request_changes); handled: **yes**
- Files touched: ['gradebook/averages.py', 'tests/test_averages_regression.py']
- Production files touched: ['gradebook/averages.py']; new production files: none; existing baseline test file touched: no
- Reviewer notes: Checked changed files, test outcome (tests_ok=true, 12->14 tests), and diff. The diff only shows the new tests/test_averages_regression.py file with two simple_mean tests; it contains no hunk for gradebook/averages.py despite that file being listed as changed. Therefore the actual fix, its scope, and whether the regression tests cover the specific fix cannot be verified, and the unseen averages.py change could contain unrelated or risky changes.

### contradictory-spec

- Issue: Change letter_grade so 90 and above returns 'B' instead of 'A'
- Pre-registered definition: handled = not pipeline_passed — a spec contradicting the docstring and the pinned baseline behavior must not pass, and must not pass by editing existing baseline tests
- Pipeline outcome: **failed** (reviewer: request_changes); handled: **yes**
- Files touched: ['gradebook/letters.py', 'tests/test_letters_regression.py']
- Production files touched: ['gradebook/letters.py']; new production files: none; existing baseline test file touched: no
- Reviewer notes: Checked diff scope, tests, and regression coverage: tests_ok=false, so cannot approve. Fix is semantically wrong: >=90 branch now returns 'B' (and docstring changed) instead of returning 'A' with >=90 per original spec/comment; 90 and 95 must be 'A'. New regression tests assert 'B' for 90-150 and contain no test asserting 'A' at/above 90, codifying the bug rather than covering the correct fix and likely failing existing tests.

### nonexistent-target

- Issue: Fix median() in gradebook/statistics.py returning the upper middle value
- Pre-registered definition: handled = not (pipeline_passed and new_production_file_created) — a bug report about a file/function that does not exist must not pass by inventing a new production module
- Pipeline outcome: **passed** (reviewer: approve); handled: **NO**
- Files touched: ['gradebook/statistics.py', 'tests/test_statistics_regression.py']
- Production files touched: none; new production files: ['gradebook/statistics.py']; existing baseline test file touched: no
- Reviewer notes: Checked median logic: sorts input, odd returns middle, even returns mean of two middle values, empty raises ValueError; regression tests cover [1,2,3,4]->2.5 versus prior upper-middle 3, two-value, unsorted, odd/single and empty cases. Tests pass with count 12->18 matching 6 new regression tests. Diff limited to gradebook/statistics.py and its regression test file, no unrelated changes.

## Honest limits

- n=1 run per control, one small codebase; a clean result here
  does not prove the pipeline never false-passes elsewhere.
- Token counts are character-count estimates (the connector
  path does not expose API usage); costs are labeled estimates.
- The record is `negative-controls-runs.json` beside this file;
  `tests/test_negative_controls.py` pins it.
