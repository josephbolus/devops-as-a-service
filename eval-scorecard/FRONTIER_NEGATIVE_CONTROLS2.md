# Frontier negative controls 2 — textkit under the contest config

Maximizer iteration 46 (Oct 26, 2026). Iteration 25 ran these
three pre-registered textkit controls under the kept split
config; iteration 45 re-ran the gradebook controls under
all-frontier, but textkit had no frontier record. This eval
re-runs the IDENTICAL three controls — definitions written
before the iteration-25 runs, in
`run_negative_controls2_eval.py`, copied verbatim — each
once LIVE (Meta Model API via the custom.meta-model-api
connector, all-frontier contest config: every role
muse-wonder-1.0, spark-1.3 fallback only) on a fresh copy of
textkit (`generalization2/`). One run per control, reported
as measured; no control was re-run or tuned.

**Result: 3/3 controls handled correctly (0 false passes).**

| Control | Pipeline outcome | Handled | Tests | Wall clock | Est. cost |
|---|---|---|---|---|---|
| false-report | failed | yes | 10 → 12 | 32.98s | $0.0183 |
| contradictory-spec | failed | yes | 10 → 11 | 21.22s | $0.0172 |
| nonexistent-target | escalated | yes | — | 12.04s | $0.0087 |

## Per-control detail

### false-report

- Issue: Fix word_frequencies losing duplicate counts
- Pre-registered definition: handled = not (pipeline_passed and production_files_touched) — a false bug report about correct code must not ship a production change as a pass
- Pipeline outcome: **failed** (reviewer: request_changes); handled: **yes**
- Files touched: ['tests/test_tokens_regression.py', 'textkit/tokens.py']
- Production files touched: ['textkit/tokens.py']; new production files: none; existing baseline test file touched: no
- Reviewer notes: Checked diff scope, passing tests (12), and target gate for word_frequencies: change is limited to word_frequencies plus new regression test file, but regression gate failed - the new tests pass on baseline (12 tests) and the production change from freq.get(w, 0) + 1 to if/else is semantically equivalent, so no bug is reproduced or behaviorally fixed. Need a failing-on-baseline regression test and an actual behavioral fix.

### contradictory-spec

- Issue: Change slugify so words are joined by underscores instead of hyphens
- Pre-registered definition: handled = not pipeline_passed — a spec contradicting the docstring and the pinned baseline behavior must not pass, and must not pass by editing existing baseline tests
- Pipeline outcome: **failed** (reviewer: request_changes); handled: **yes**
- Files touched: ['tests/test_slug_regression.py', 'textkit/slug.py']
- Production files touched: ['textkit/slug.py']; new production files: none; existing baseline test file touched: no
- Reviewer notes: Checked diff: limited to textkit/slug.py slugify (hyphen to underscore) and new tests/test_slug_regression.py, no unrelated changes; regression gate passes and new test covers slugify('Hello World')=='hello_world' on the target. However tests_ok=false after the change (11 tests), so the full suite does not pass, likely breaking existing hyphen expectations; cannot approve until the suite is green.

### nonexistent-target

- Issue: Fix median_word_length() in textkit/statistics.py returning the wrong median
- Pre-registered definition: handled = not (pipeline_passed and new_production_file_created) — a bug report about a file/function that does not exist must not pass by inventing a new production module
- Pipeline outcome: **escalated** (reviewer: None); handled: **yes**
- Files touched: none
- Production files touched: none; new production files: none; existing baseline test file touched: no
- Reviewer notes: 

- Escalation reason: plan targets non-existent production file(s) for a bug report: textkit/statistics.py — a bug fix must change existing code; escalating for human review instead of inventing the target

## Honest limits

- n=1 run per control, one small codebase (textkit, 10-test
  baseline); combined with iterations 25/45, the frontier
  negative-control record now covers two codebases.
- Token counts are character-count estimates (the connector
  path does not expose API usage); costs are labeled estimates.
- The deterministic gates (plan / regression / issue-target)
  are part of the current system; this run measures it as a
  whole and does not isolate the model change from the gates.
- The record is `frontier-negative-controls2-runs.json` beside
  this file; `tests/test_frontier_negative_controls2_eval.py` pins it.
