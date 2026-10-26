# Frontier generalization -- the contest configuration on an unseen codebase (Oct 26, 2026)

Maximizer iteration 33. Every earlier generalization pass (ledgerlite, textkit, gradebook) ran under the Oct 25 kept split config, and every all-frontier pass (iterations 31/32) ran only on the seeded demo set -- so the contest configuration (all four roles on `muse-wonder-1.0`, per Joseph's Oct 26 directive; `muse-spark-1.3` configured only as availability fallback) had never been measured outside the seeded set. This file is that measurement: the hardest existing generalization target, run live under the contest configuration, reported as measured.

## The target

`generalization3/` vendors **gradebook** (12-test baseline): two defects in two production modules -- `weighted_mean` in `gradebook/averages.py` divides by `len(values)` instead of the sum of the weights (baseline repro 170.0, expected 85.0), and `letter_grade` in `gradebook/letters.py` uses `> 90` instead of `>= 90` (baseline repro `letter_grade(90)` returns 'B', expected 'A'). The vendored copy was not tuned after the run and still reproduces both bugs in place; the pipeline ran against a fresh git-initialized copy.

## Measured live run (connector, all-frontier contest config)

- Outcome: **passed** (pipeline: passed; independent probe: 8/8 checks passed)
- Tests: 12 -> 18 (growth +6)
- Wall clock: 32.87s
- Model calls: 4; models by role: CODER=muse-wonder-1.0, PLANNER=muse-wonder-1.0, REVIEWER=muse-wonder-1.0, TRIAGE=muse-wonder-1.0
- Est. API cost: $0.0340 (char estimate at wonder prices $4/$20 per 1M)
- Reviewer: approve
- Files touched: gradebook/averages.py, gradebook/letters.py, tests/test_averages_regression.py, tests/test_letters_regression.py
- Production files touched: gradebook/averages.py, gradebook/letters.py
- Unexpected files: none
- Fallbacks: 0 (successes 0); retries: 0

## Comparison with the same target under the split (iteration 23)

- Split pass (source: eval-scorecard/generalization3-runs.json (maximizer iteration 23, kept split config)): outcome passed, tests 12 -> 18 (+6), 42.41s, est. $0.0248, probe passed: True.
- All-frontier pass (this run): outcome passed, tests 12 -> 18, 32.87s, est. $0.0340, probe passed: True.

Verdict (computed from the measured run): The contest configuration generalized: the all-frontier pipeline passed end to end on an unseen multi-file codebase and the independent probe passed, so the frontier record is no longer seeded-set-only. This is one run on one synthetic target already used for the split-config generalization record -- it does not add a new codebase or a real-team claim.

Honest limits: one live run, on a small synthetic package written for this evaluation family (n=1 issue); no real users/backlog; review time remains the IMPACT_MODEL.md assumption. Costs are character estimates, not provider-reported usage. No tool calling or responses-endpoint surface is claimed -- the connector helper offers chat completions only.
