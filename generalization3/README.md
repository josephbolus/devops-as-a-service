# gradebook — third generalization target codebase (multi-file)

A small, self-contained Python package (stdlib only) vendored into
this repo on Oct 25, 2026 **solely** as a FOURTH codebase the DevOps
as a Service pipeline has never seen (after the seeded demo repo,
`generalization/`'s ledgerlite, and `generalization2/`'s textkit):
a different package name (`gradebook`), a different domain (course
grading — weighted means, letter grades, grade reports), and a
different module layout (`averages` / `letters` / `report`).

It differs from both earlier generalization targets in shape, not
just name: its issue carries **two defects in two different
production modules**, so a passing run must plan and edit more than
one production file — every earlier live fix touched exactly one.

## The pre-existing bugs

1. `gradebook/averages.py` — `weighted_mean()` divides by
   `len(values)` instead of the sum of the weights, contradicting
   its docstring. Repro: `weighted_mean([80, 100], [3, 1])` returns
   `170.0`, expected `85.0`. The baseline suite only uses weights
   whose sum equals the count, so it passes with the bug present.
2. `gradebook/letters.py` — `letter_grade()` uses `score > 90` for
   an A instead of `>= 90`, contradicting its docstring. Repro:
   `letter_grade(90)` returns `'B'`, expected `'A'`. The baseline
   suite never tests exactly 90, so it passes with the bug present.

```bash
python3 -m unittest discover -s tests -q   # 12 tests, all passing
```

## The issue

`issue.json` in this directory is the real issue the pipeline was
run against (title: "Fix weighted_mean denominator and the
90-point letter-grade boundary"). The measured live run and its
outcome are recorded in `../eval-scorecard/GENERALIZATION3.md` and
`../eval-scorecard/generalization3-runs.json`. The record also
carries an **independent probe**: after the pipeline finished,
checks written for this evaluation (not by the pipeline, not part
of its own test suite) were run against the fixed copy, so the
pipeline's own regression tests are not the only evidence that
both defects are actually fixed.

This directory is the pristine pre-run state: the pipeline ran
against a fresh copy of it, never against this directory in place,
and it was not tuned after the run — whatever the run did is the
recorded result.
