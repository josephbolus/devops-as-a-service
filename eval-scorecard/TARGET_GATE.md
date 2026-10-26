# Target-gate recheck — the off-target false pass, re-run post-fix

Maximizer iteration 27 (Oct 26, 2026). The regression-gate-2
eval (`REGRESSION_GATE2.md`) measured the gradebook
`false-report` control as a **false pass**: for a false claim
about `simple_mean`, the coder fixed the genuine
`weighted_mean` bug in the same file instead, the regression
gate verified that real change, the reviewer approved, tests
grew 12 → 16, and the run passed without touching the
function the issue was about. That record stands unaltered.

Fix: a deterministic issue-target gate in `daas/pipeline.py`
— when the issue names existing repo functions, a run may
pass only if the production change actually modifies at
least one of them (function source segments compared between
the baseline and after snapshots; not applicable when the
issue names no existing function), pinned by
`tests/test_target_gate.py`.

**Recheck result: outcome `failed`, handled: NO** (wall clock 50.44s, tests 12 → 14, reviewer request_changes).

- Target gate: {'applicable': True, 'passed': True, 'mentioned_targets': ['simple_mean'], 'changed_functions': ['simple_mean'], 'reason': "the fix changes the issue's named target(s): simple_mean"}
- Regression gate: {'applicable': True, 'passed': False, 'tests_ok_on_baseline': True, 'tests_on_baseline': 14, 'reason': 'suite passes on baseline production code, so the new tests do not demonstrate any change — the claimed bug is not reproduced by them'}

In this re-run the coder stayed ON target (the `simple_mean` segment changed), so the target gate passed and there was no off-target drift for it to block; the run was instead blocked deterministically by the regression gate (the coder's behavior-preserving refactor left the suite passing on the baseline) and the reviewer requested changes. The recheck's pre-registered handled definition required a TARGET-gate block specifically, so it records handled: NO — while the combined gate system did stop the false report. The off-target shape itself is blocked deterministically in the test-pinned mock/helper tests (`tests/test_target_gate.py`); whether a live coder drifts off target varies run to run.
- Files touched: ['gradebook/averages.py', 'tests/test_averages_regression.py']
- Reviewer notes: Checked diff scope (only gradebook/averages.py simple_mean and new test file; no unrelated changes), target gate (simple_mean changed), and tests_ok=true with 14 tests passing. However regression_gate failed: suite also passes (14) on baseline production code, and the change is a behavior-preserving refactor (total=sum(scores); return total/len(scores)), so the new tests do not reproduce the claimed bug and no functional fix is demonstrated. Need a regression test that fails on baseline and a corresponding behavioral fix.

## Honest limits

- One re-run of one control under the new code; the gate is
  also test-pinned in mock mode (genuine Tier-1 passes, an
  off-target stub client cannot pass).
- The gate only fires when the issue names an existing
  function as a whole word; issues that describe behaviour
  without naming a function are not applicable and rely on
  the other gates and the reviewer, as before.
- Token counts are character-count estimates (the connector
  path does not expose API usage); costs are labeled estimates.
- The record is `target-gate-recheck.json` beside this file;
  `tests/test_regression_gate2_eval.py` pins both records.
