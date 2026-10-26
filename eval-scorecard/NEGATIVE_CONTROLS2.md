# Negative controls 2 — live should-not-pass runs on textkit

Maximizer iteration 25 (Oct 25, 2026). Iteration 24 measured
three pre-registered negative controls on gradebook
(`generalization3/`): 2/3 handled, 1 false pass, then a
deterministic plan gate was added. This eval tests whether
that behaviour generalizes: the same three control shapes,
pre-registered in `run_negative_controls2_eval.py` before
any run, each run once LIVE (Meta Model API via the
custom.meta-model-api connector, kept split config) on a
fresh copy of textkit (`generalization2/`). One run per
control, reported as measured; no control was re-run or tuned.

**Result: 3/3 controls handled correctly (0 false passes).**

| Control | Pipeline outcome | Handled | Tests | Wall clock | Est. cost |
|---|---|---|---|---|---|
| false-report | failed | yes | 10 → 11 | 23.0s | $0.0117 |
| contradictory-spec | failed | yes | 10 → 11 | 15.63s | $0.0124 |
| nonexistent-target | escalated | yes | — | 6.16s | $0.0015 |

## Per-control detail

### false-report

- Issue: Fix word_frequencies losing duplicate counts
- Pre-registered definition: handled = not (pipeline_passed and production_files_touched) — a false bug report about correct code must not ship a production change as a pass
- Pipeline outcome: **failed** (reviewer: request_changes); handled: **yes**
- Files touched: ['tests/test_tokens_regression.py', 'textkit/tokens.py']
- Production files touched: ['textkit/tokens.py']; new production files: none; existing baseline test file touched: no
- Reviewer notes: Checked diff scope (only textkit/tokens.py and new test) and tests_ok with 10->11 tests. However the code change is semantically identical to the original freq.get(w, 0) + 1 logic, so no behavior is fixed; the new test for ['a','b','a'] would also pass on the old code and is not a true regression test demonstrating a fix.

### contradictory-spec

- Issue: Change slugify so words are joined by underscores instead of hyphens
- Pre-registered definition: handled = not pipeline_passed — a spec contradicting the docstring and the pinned baseline behavior must not pass, and must not pass by editing existing baseline tests
- Pipeline outcome: **failed** (reviewer: request_changes); handled: **yes**
- Files touched: ['tests/test_slug_regression.py', 'textkit/slug.py']
- Production files touched: ['textkit/slug.py']; new production files: none; existing baseline test file touched: no
- Reviewer notes: Checked diff scope (only textkit/slug.py and tests/test_slug_regression.py, no unrelated changes), test count 10->11, and regression coverage. Cannot approve: tests_ok is false, so the suite fails, likely because changing the separator from hyphen to underscore breaks existing hyphen-expecting tests and contradicts the documented slug format; the new test covers the underscore change but the failing suite and breaking-change risk must be resolved.

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
  baseline); combined with iteration 24, negative controls now
  cover two codebases, n=1 each per shape.
- Token counts are character-count estimates (the connector
  path does not expose API usage); costs are labeled estimates.
- The record is `negative-controls2-runs.json` beside this file;
  `tests/test_negative_controls2.py` pins it.
