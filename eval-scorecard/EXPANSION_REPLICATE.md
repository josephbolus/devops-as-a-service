# Expansion replicate -- all nine expansion issues, second live pipeline pass (Oct 26, 2026)

Maximizer iteration 44. Iterations 35-37 seeded the nine
expansion scenario families (spec issues #4-#12) and ran each
once LIVE through the pipeline under the all-frontier contest
configuration: 9/9 passed, growth +32. The stated cap on that
record was one direct pipeline pass per issue (the iteration-41
Judge Mode tour was a second live exposure through the console
path, a different harness). This file is the direct-pipeline
replicate: all nine issues run a second time, reported as
measured, NOT re-run for a cleaner record.

Baseline note: batches 1/2 originally ran at 12/18-test
baselines (seeding grew the repo batch by batch); this
replicate runs all nine at the current 24-test baseline.
Pass/fail and growth deltas are comparable; absolute counts
carry that caveat.

## Replicate pass (iteration 44, all-frontier)

- config-drift (#4 configuration drift): **passed** -- tests 24 -> 29, 19.4s, est. cost $0.0291 (char estimate at wonder prices $4/$20 per 1M)
- health-check (#8 health-check correctness): **passed** -- tests 24 -> 28, 23.57s, est. cost $0.0293 (char estimate at wonder prices $4/$20 per 1M)
- alert-threshold (#9 alerting defect): **passed** -- tests 24 -> 27, 14.22s, est. cost $0.0198 (char estimate at wonder prices $4/$20 per 1M)
- connection-pool (#6 database connection-pool leak): **passed** -- tests 24 -> 28, 18.98s, est. cost $0.0309 (char estimate at wonder prices $4/$20 per 1M)
- log-rotation (#7 resource exhaustion (disk / log rotation)): **passed** -- tests 24 -> 27, 33.53s, est. cost $0.0385 (char estimate at wonder prices $4/$20 per 1M)
- scheduled-job (#12 scheduled job silently skips): **passed** -- tests 24 -> 27, 21.0s, est. cost $0.0331 (char estimate at wonder prices $4/$20 per 1M)
- retry-storm (#5 cascading failure / retry storm): **passed** -- tests 24 -> 27, 23.07s, est. cost $0.0329 (char estimate at wonder prices $4/$20 per 1M)
- deploy-token (#10 CI/CD expired-token handling): **passed** -- tests 24 -> 27, 19.13s, est. cost $0.0329 (char estimate at wonder prices $4/$20 per 1M)
- api-pagination (#11 upstream API pagination compatibility): **passed** -- tests 24 -> 27, 28.86s, est. cost $0.0262 (char estimate at wonder prices $4/$20 per 1M)

Replicate summary: issues passed 9/9; total test growth +31; total wall clock 201.76s; total est. cost $0.2726; est. cost per passed issue $0.0303.

## Two-pass comparison (expansion set, direct pipeline)

- Iterations 35-37 pass: issues 9/9, growth +32, 211.8s, est. $0.2666 (source: eval-scorecard/expansion-batch{1,2,3}-runs.json (maximizer iterations 35-37))
- Iteration 44 replicate: issues 9/9, growth +31, 201.76s, est. $0.2726, at the 24-test baseline
- Combined: growth each [32, 31], mean +31.5, range +31 to +32; all nine issues passed on both passes: True.

Verdict (computed from the two measured passes): The replicate repeats the expansion record at the outcome level -- 9/9 passed again -- so the expansion set's direct-pipeline record is now two passes, 18/18 issue-runs, and its one-live-pass cap is removed. Growth deltas per pass are stated above as measured.

Honest limits: two direct pipeline passes per expansion issue
on the seeded demo codebase; no real users or real backlog,
and review time is still the impact model's 10-minute
assumption. Costs are character estimates, not
provider-reported usage.
