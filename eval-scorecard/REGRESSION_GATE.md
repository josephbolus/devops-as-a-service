# Regression gate — live positive + false-report controls on textkit

Maximizer iteration 26 (Oct 25, 2026). Iterations 24–25
measured that false bug reports were stopped only by the
reviewer. Iteration 26 adds a deterministic regression gate
to `daas/pipeline.py`: changed production files are restored
to baseline, the suite is re-run with the coder's tests in
place, and a run may pass only if that suite FAILS on the
baseline. This eval ran the two pre-registered controls in
`run_regression_gate_eval.py` once each LIVE (Meta Model API
via the custom.meta-model-api connector, kept split config)
on fresh copies of textkit (`generalization2/`).

**Result: 2/2 controls behaved as pre-registered.**

| Control | Pipeline outcome | Gate | Tests | Wall clock | Est. cost |
|---|---|---|---|---|---|
| positive-genuine-bug | passed | verified (fails on baseline) | 10 → 14 | 20.48s | $0.0131 |
| false-report | failed | BLOCKED (passes on baseline) | 10 → 13 | 29.54s | $0.0141 |

## Per-control detail

### positive-genuine-bug

- Issue: Fix first_words returning one word too many
- Pre-registered expectation: expected: pipeline_passed AND gate applicable AND suite fails on baseline (gate verified)
- Pipeline outcome: **passed** (reviewer: approve); as pre-registered: **yes**
- Regression gate: {'applicable': True, 'passed': True, 'tests_ok_on_baseline': False, 'tests_on_baseline': 14, 'reason': 'suite fails on baseline production code, so the new tests demonstrate the claimed change'}
- Files touched: ['tests/test_tokens_regression.py', 'textkit/tokens.py']
- Reviewer notes: Checked diff: single-line fix in textkit/tokens.py (words[:n+1] to words[:n]) with no unrelated changes; tests pass (10 to 14) and regression_gate passed with suite failing on baseline; new tests in tests/test_tokens_regression.py cover exact count, n=1, non-positive, and fewer-than-n cases.

### false-report

- Issue: Fix word_frequencies losing duplicate counts
- Pre-registered expectation: expected: NOT pipeline_passed AND gate blocks it deterministically (gate applicable, suite passes on baseline, gate passed == False)
- Pipeline outcome: **failed** (reviewer: request_changes); as pre-registered: **yes**
- Regression gate: {'applicable': True, 'passed': False, 'tests_ok_on_baseline': True, 'tests_on_baseline': 13, 'reason': 'suite passes on baseline production code, so the new tests do not demonstrate any change — the claimed bug is not reproduced by them'}
- Files touched: ['tests/test_tokens_regression.py', 'textkit/tokens.py']
- Reviewer notes: Checked diff scope and tests: tests pass (13 after vs 10 before) and changes are limited to textkit/tokens.py and tests/test_tokens_regression.py, but regression gate failed - suite also passes on baseline (13 tests), so new tests do not reproduce the claimed bug. The production change from freq.get(w,0)+1 to if/else is functionally equivalent/no-op, so no fix is demonstrated; a regression test that fails on baseline and passes after a real fix is missing.

## Honest limits

- n=1 run per control, one small codebase (textkit, 10-test
  baseline). The gate checks the suite as a whole: a run with
  one baseline-failing test among baseline-passing ones is
  verified — per-test granularity is not claimed.
- The reviewer receives the gate result as context and
  cited it in its notes on both runs; the gate's block does
  not depend on the reviewer — `passed` is computed
  deterministically in code from the baseline re-run.
- The gate applies only when both production and test files
  changed; other change shapes record it as not applicable.
- Token counts are character-count estimates (the connector
  path does not expose API usage); costs are labeled estimates.
- The record is `regression-gate-runs.json` beside this file;
  `tests/test_regression_gate_eval.py` pins it.
