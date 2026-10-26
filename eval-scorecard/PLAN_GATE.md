# Plan-gate recheck — the false-passed control, re-run post-fix

Maximizer iteration 24 (Oct 25, 2026). The negative-controls
eval (`NEGATIVE_CONTROLS.md`) measured the `nonexistent-target`
control as a **false pass**: the pipeline invented
`gradebook/statistics.py` to "fix" a `median()` that does not
exist, tests grew 12 → 18, and the reviewer approved. That
record stands unaltered.

Fix: a deterministic plan gate in `daas/pipeline.py` — for a
bug report, a plan naming a non-test production file that is
not in the repo tree escalates BEFORE the coder runs (feature
requests exempt; new test files exempt), pinned by
`tests/test_plan_gate.py`.

**Recheck result: outcome `escalated`, handled: yes** (wall clock 14.14s, model calls 2).

Escalation reason: plan targets non-existent production file(s) for a bug report: gradebook/statistics.py — a bug fix must change existing code; escalating for human review instead of inventing the target

## Honest limits

- One re-run of one control under the new code; the gate is
  deterministic given the plan, but whether the planner names
  the invented file can vary by run — the unit tests pin the
  gate itself, this record shows one live pass through it.
- The original false-pass record is not erased or re-scored
  away: it is why the gate exists.
- Record: `negative-controls-recheck.json` beside this file;
  pinned by `tests/test_negative_controls.py`.
