# Frontier generalization (textkit) -- the contest configuration on unseen codebase #2 (Oct 26, 2026)

Maximizer iteration 39. Iterations 33 and 38 measured the all-frontier contest configuration (all four roles on `muse-wonder-1.0`, per Joseph's Oct 26 directive; `muse-spark-1.3` configured only as availability fallback) on two unseen codebases (gradebook and ledgerlite). Textkit -- the second unseen codebase (iteration 19) -- was the last split-only target. This file is that missing measurement, reported as measured.

## The target

`generalization2/` vendors **textkit** (10-test baseline): `first_words()` in `textkit/tokens.py` slices `words[:n+1]` and returns one word more than requested (baseline repro `first_words('alpha beta gamma delta', 2)` returns 'alpha beta gamma', expected 'alpha beta'). The vendored copy was not tuned after the run and still reproduces the bug in place; the pipeline ran against a fresh git-initialized copy.

## Measured live run (connector, all-frontier contest config)

- Outcome: **passed** (pipeline: passed; independent probe: 7/7 checks passed)
- Tests: 10 -> 11 (growth +1)
- Wall clock: 18.14s
- Model calls: 4; models by role: CODER=muse-wonder-1.0, PLANNER=muse-wonder-1.0, REVIEWER=muse-wonder-1.0, TRIAGE=muse-wonder-1.0
- Est. API cost: $0.0168 (char estimate at wonder prices $4/$20 per 1M)
- Reviewer: approve
- Files touched: tests/test_tokens_regression.py, textkit/tokens.py
- Production files touched: textkit/tokens.py
- Unexpected files: none
- Fallbacks: 0 (successes 0); retries: 0

## Comparison with the same target under the split (iteration 19)

- Split pass (source: eval-scorecard/generalization2-runs.json (maximizer iteration 19, kept split config)): outcome passed, tests 10 -> 15 (+5), 31.98s, est. $0.0144.
- All-frontier pass (this run): outcome passed, tests 10 -> 11, 18.14s, est. $0.0168, probe passed: True.

Verdict (computed from the measured run): The contest configuration generalized to a third unseen codebase: frontier generalization now rests on gradebook (multi-file, iteration 33), ledgerlite (iteration 38) and textkit (this run), each probe-verified -- every unseen codebase now has an all-frontier record. This is one run on a small synthetic target already used for the split record -- it does not add a new codebase or a real-team claim.

Honest limits: one live run, on a small synthetic package written for this evaluation family (n=1 issue); no real users/backlog; review time remains the IMPACT_MODEL.md assumption. Costs are character estimates, not provider-reported usage.
