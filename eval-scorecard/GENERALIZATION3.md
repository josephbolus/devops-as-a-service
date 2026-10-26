# Generalization run 3 — a fourth codebase, and the first multi-file fix

Maximizer iteration 23, Oct 25, 2026 (item-4 polish: new evidence, not
re-presentation). Machine-readable record: `generalization3-runs.json`
next to this file. Runner:
`hackathon-agent-scaffold/run_generalization3_eval.py`.

## Why

Iterations 15 and 19 proved the pipeline live on two unseen
codebases — but every live fix so far, seeded or generalization,
touched exactly **one** production file and fixed exactly **one**
defect. Real backlog issues are not always shaped like that. This
run tests the next shape: an unseen codebase whose issue carries
**two defects in two different production modules**, so the planner
must name both files and the coder must fix both — a partial fix is
a failing run.

## The target

`generalization3/` vendors **gradebook**, a small stdlib-only Python
package created for this run and never previously run through the
pipeline. It differs from all three earlier codebases:

- package name `gradebook/` vs the demo repo's `app/`, `ledgerlite/`
  and `textkit/`
- domain: course grading (weighted means, letter grades, grade
  reports) vs pagination/HTTP/CLI reports, ledger cent amounts, and
  text normalization/tokens/slugs
- module layout: `averages` / `letters` / `report`
- baseline suite 12 tests (demo repo baseline: 6, ledgerlite: 9,
  textkit: 10)
- no MockClient canned response exists for this issue — live-only

Its two genuine pre-existing bugs, each contradicting its own
docstring:

1. `weighted_mean()` in `gradebook/averages.py` divided by
   `len(values)` instead of the sum of the weights. Baseline repro:
   `weighted_mean([80, 100], [3, 1])` returned `170.0`, expected
   `85.0`. The baseline suite only uses weights whose sum equals
   the count, so it passed 12/12 with the bug present.
2. `letter_grade()` in `gradebook/letters.py` used `score > 90`
   for an A instead of `>= 90`. Baseline repro: `letter_grade(90)`
   returned `'B'`, expected `'A'`. The baseline suite never tests
   exactly 90, so it passed with the bug present.

The vendored copy was not tuned after the run — the pipeline ran
against a fresh git-initialized copy, and the vendored copy still
reproduces both bugs in place.

The issue: "Fix weighted_mean denominator and the 90-point
letter-grade boundary" (`generalization3/issue.json`).

## The measured live run (connector, kept split config)

Run at 2026-10-26T02:57:16Z through the custom.meta-model-api
connector (no env key), CODER/REVIEWER on muse-wonder-1.0 and
TRIAGE/PLANNER on muse-spark-1.3 — the entry's kept live
configuration, recorded per call in `generalization3-runs.json`.

| | |
|---|---|
| Outcome | **passed** (pipeline pass AND independent probe pass) |
| Tests | 12 → 18 discovered (+6) |
| Wall clock | 42.41s |
| Model calls | 4 (one per role) |
| Est. API cost | $0.0248 (char estimate, see COST_ACCOUNTING.md) |
| Reviewer | approve |
| Files touched | `gradebook/averages.py`, `gradebook/letters.py`, `tests/test_gradebook_regression.py` |
| Production files touched | both defective modules |
| Unexpected files | none |

The fixes are one line each — divide by `total_weight`; `score >= 90`
for an A — and the coder added a new regression file with six tests
covering the weighted-mean denominator (including the empty and
zero-weight cases), the 90-point boundary and the other inclusive
thresholds, and both end-to-end `final_letter` combinations. (The
coder's regression file locates `final_letter` through a small
fallback loader rather than importing `gradebook.report` directly;
the probe below imports it directly, so the end-to-end behavior is
verified independently of that choice.)

## The independent probe

The pipeline's own regression tests are not the only evidence. After
the run, eight checks written for this evaluation — not by the
pipeline, not part of its test suite — were run against the fixed
copy: **8/8 passed**, including `weighted_mean([80, 100], [3, 1])
== 85.0`, `weighted_mean([70, 90], [1, 3]) == 85.0`,
`letter_grade(90) == 'A'`, `letter_grade(89.9) == 'B'`,
`final_letter([90, 90], [1, 1]) == 'A'`, and
`final_letter([80, 100], [3, 1]) == 'B'`, plus two unchanged-case
guards. The run only counts as passed because the probe passed;
the full probe is in `generalization3-runs.json`.

## What this does and does not prove

Combined with iterations 15 and 19, the pipeline has now passed
live, end to end, on **three** codebases it had never seen, in three
domains, with three bug shapes — and, for the first time, a run
whose planner and coder had to span two production files to pass,
verified by an independent probe rather than the pipeline's own
tests alone. It does NOT prove performance on a real team's
codebase: all three targets are still small synthetic packages
written for this evaluation (n=1 issue each, one run each), there
are still no real users, and review time remains the
IMPACT_MODEL.md assumption. Those caps stand; the
single-production-file cap does not.
