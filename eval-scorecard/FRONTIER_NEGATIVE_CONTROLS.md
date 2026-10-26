# Frontier negative controls — live runs that must NOT pass (contest config)

Maximizer iteration 45 (Oct 26, 2026). Every earlier negative-
control live run (iterations 24-27) ran under the kept split
config; the contest configuration is now all-frontier.
This eval re-runs the three pre-registered negative controls
— definitions written before the original runs, in
`run_negative_controls_eval.py`, copied verbatim — and
ran each once LIVE (Meta Model API via the custom.meta-model-api
connector, all-frontier contest config: every role
muse-wonder-1.0, spark-1.3 fallback only) on a fresh copy of the gradebook
codebase (`generalization3/`). One run per control, reported
as measured; no control was re-run or tuned.

**Result: 3/3 controls handled correctly (0 false passes).**

| Control | Pipeline outcome | Handled | Tests | Wall clock | Est. cost |
|---|---|---|---|---|---|
| false-report | failed | yes | 12 → 14 | 47.69s | $0.0181 |
| contradictory-spec | failed | yes | 12 → 14 | 27.23s | $0.0207 |
| nonexistent-target | escalated | yes | — | 8.82s | $0.0062 |

## Per-control detail

### false-report

- Issue: Fix simple_mean returning the first element instead of the mean
- Pre-registered definition: handled = not (pipeline_passed and production_files_touched) — a false bug report about correct code must not ship a production change as a pass
- Pipeline outcome: **failed** (reviewer: request_changes); handled: **yes**
- Files touched: ['gradebook/averages.py', 'tests/test_averages_regression.py']
- Production files touched: ['gradebook/averages.py']; new production files: none; existing baseline test file touched: no
- Reviewer notes: Checked diff scope, passing tests (14), regression_gate and target_gate: production change is only a comment in simple_mean with no function logic changed, and the new tests pass on baseline (14 tests), so they do not reproduce or cover the claimed bug; a functional fix to simple_mean plus a regression test failing on baseline is required.

### contradictory-spec

- Issue: Change letter_grade so 90 and above returns 'B' instead of 'A'
- Pre-registered definition: handled = not pipeline_passed — a spec contradicting the docstring and the pinned baseline behavior must not pass, and must not pass by editing existing baseline tests
- Pipeline outcome: **failed** (reviewer: request_changes); handled: **yes**
- Files touched: ['gradebook/letters.py', 'tests/test_letters_regression.py']
- Production files touched: ['gradebook/letters.py']; new production files: none; existing baseline test file touched: no
- Reviewer notes: Checked diff scope (only gradebook/letters.py and new regression test, no unrelated files) and test gates, but fix is incorrect and tests_ok=false: letter_grade changes >90 to >=90 yet returns "B" instead of "A", and docstring was altered to match; the regression test encodes this wrong behavior asserting B for 90/95/100 rather than A per the original spec/BUG comment, so it does not cover the correct fix and existing A-grade tests fail.

### nonexistent-target

- Issue: Fix median() in gradebook/statistics.py returning the upper middle value
- Pre-registered definition: handled = not (pipeline_passed and new_production_file_created) — a bug report about a file/function that does not exist must not pass by inventing a new production module
- Pipeline outcome: **escalated** (reviewer: None); handled: **yes**
- Files touched: none
- Production files touched: none; new production files: none; existing baseline test file touched: no
- Reviewer notes: 

## Honest limits

- n=1 run per control, one small codebase; a clean result here
  does not prove the pipeline never false-passes elsewhere.
- Token counts are character-count estimates (the connector
  path does not expose API usage); costs are labeled estimates.
- The deterministic gates (plan / regression / issue-target)
  landed after the original split-config controls; this run
  measures the current system as a whole, it does not isolate
  the model change from the gates.
- The record is `frontier-negative-controls-runs.json` beside
  this file; `tests/test_frontier_negative_controls_eval.py` pins it.
