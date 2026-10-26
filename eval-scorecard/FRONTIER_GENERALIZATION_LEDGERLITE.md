# Frontier generalization (ledgerlite) -- the contest configuration on unseen codebase #1 (Oct 26, 2026)

Maximizer iteration 38. Iteration 33 measured the all-frontier contest configuration (all four roles on `muse-wonder-1.0`, per Joseph's Oct 26 directive; `muse-spark-1.3` configured only as availability fallback) on one unseen codebase (gradebook). Ledgerlite -- the first unseen codebase (iteration 15) -- still only had a split-config record. This file is that missing measurement, reported as measured.

## The target

`generalization/` vendors **ledgerlite** (9-test baseline): `median_cents()` in `ledgerlite/stats.py` returns the upper middle value for even-length inputs instead of averaging the two middle values (baseline repro 300, expected 250). The vendored copy was not tuned after the run and still reproduces the bug in place; the pipeline ran against a fresh git-initialized copy.

## Measured live run (connector, all-frontier contest config)

- Outcome: **passed** (pipeline: passed; independent probe: 6/6 checks passed)
- Tests: 9 -> 11 (growth +2)
- Wall clock: 18.51s
- Model calls: 4; models by role: CODER=muse-wonder-1.0, PLANNER=muse-wonder-1.0, REVIEWER=muse-wonder-1.0, TRIAGE=muse-wonder-1.0
- Est. API cost: $0.0177 (char estimate at wonder prices $4/$20 per 1M)
- Reviewer: approve
- Files touched: ledgerlite/stats.py, tests/test_stats_regression.py
- Production files touched: ledgerlite/stats.py
- Unexpected files: none
- Fallbacks: 0 (successes 0); retries: 0

## Comparison with the same target under the split (iteration 15)

- Split pass (source: eval-scorecard/generalization-runs.json (maximizer iteration 15, kept split config)): outcome passed, tests 9 -> 13 (+4), 37.73s, no recorded cost (the pass predates cost accounting).
- All-frontier pass (this run): outcome passed, tests 9 -> 11, 18.51s, est. $0.0177, probe passed: True.

Verdict (computed from the measured run): The contest configuration generalized to a second unseen codebase: frontier generalization now rests on gradebook (multi-file, iteration 33) and ledgerlite (this run), each probe-verified. Textkit remains split-only. This is one run on a small synthetic target already used for the split record -- it does not add a new codebase or a real-team claim.

Honest limits: one live run, on a small synthetic package written for this evaluation family (n=1 issue); no real users/backlog; review time remains the IMPACT_MODEL.md assumption. Costs are character estimates, not provider-reported usage.
