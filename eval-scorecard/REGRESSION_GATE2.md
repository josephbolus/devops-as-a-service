# Regression gate 2 — live multi-file positive + false-report controls on gradebook

Maximizer iteration 27 (Oct 26, 2026). Iteration 26 validated
the deterministic regression gate live on one codebase
(textkit) with single-file changes. This eval ran the two
pre-registered controls in `run_regression_gate2_eval.py`
once each LIVE (Meta Model API via the custom.meta-model-api
connector, kept split config) on fresh copies of gradebook
(`generalization3/`, 12-test baseline) — including the first
multi-file gate validation: the genuine fix touches two
production modules, so the gate must restore both to
baseline, see the suite fail, and restore both fixes.

**Result: 1/2 controls behaved as pre-registered.**

| Control | Pipeline outcome | Gate | Tests | Wall clock | Est. cost |
|---|---|---|---|---|---|
| positive-genuine-multi-file | passed | verified (fails on baseline) | 12 → 17 | 56.57s | $0.0244 |
| false-report | passed | verified (fails on baseline) | 12 → 16 | 71.8s | $0.0129 |

## Per-control detail

### positive-genuine-multi-file

- Issue: Fix weighted_mean denominator and the 90-point letter-grade boundary
- Pre-registered expectation: expected: pipeline_passed AND gate applicable AND gate passed (suite fails on baseline) AND both production files touched
- Pipeline outcome: **passed** (reviewer: approve); as pre-registered: **yes**
- Regression gate: {'applicable': True, 'passed': True, 'tests_ok_on_baseline': False, 'tests_on_baseline': 17, 'reason': 'suite fails on baseline production code, so the new tests demonstrate the claimed change'}
- Files touched: ['gradebook/averages.py', 'gradebook/letters.py', 'tests/test_gradebook_regression.py']
- Production files touched: ['gradebook/averages.py', 'gradebook/letters.py']
- Reviewer notes: Checked diff limited to planned scope: weighted_mean now divides by total_weight in averages.py and letter_grade uses >=90 in letters.py, no unrelated changes. Tests pass (12->17) and regression gate passes (fails on baseline). New tests/test_gradebook_regression.py covers weighted_mean weight division/equal weights, exact-90 A boundary, other thresholds, and end-to-end cases.

### false-report

- Issue: Fix simple_mean returning the first element instead of the mean
- Pre-registered expectation: expected: NOT pipeline_passed AND gate blocks it deterministically (gate applicable, suite passes on baseline, gate passed == False)
- Pipeline outcome: **passed** (reviewer: approve); as pre-registered: **NO**
- Regression gate: {'applicable': True, 'passed': True, 'tests_ok_on_baseline': False, 'tests_on_baseline': 16, 'reason': 'suite fails on baseline production code, so the new tests demonstrate the claimed change'}
- Files touched: ['gradebook/averages.py', 'tests/test_averages_regression.py']
- Production files touched: ['gradebook/averages.py']
- Reviewer notes: Checked diff limited to gradebook/averages.py weighted_mean fix (divide by total_weight) plus new tests/test_averages_regression.py; no unrelated changes. Tests pass (12 to 16) and regression gate passed: suite fails on baseline, with test_weighted_mean_divides_by_total_weight covering the fix.

## Honest limits

- n=1 run per control. Combined with iteration 26, the gate
  now has live controls on two codebases (textkit and
  gradebook), including one multi-file fix — still small
  synthetic packages, no real-team workload.
- The gate checks the suite as a whole: a run with one
  baseline-failing test among baseline-passing ones is
  verified — per-test granularity is not claimed.
- The reviewer receives the gate result as context; the
  gate's block does not depend on the reviewer — `passed` is
  computed deterministically in code from the baseline re-run.
- The gate applies only when both production and test files
  changed; other change shapes record it as not applicable.
- Token counts are character-count estimates (the connector
  path does not expose API usage); costs are labeled estimates.
- The record is `regression-gate2-runs.json` beside this file;
  `tests/test_regression_gate2_eval.py` pins it. The
  iteration-26 textkit record stands unaltered.
