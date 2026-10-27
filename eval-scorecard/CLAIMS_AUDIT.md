# Claims audit -- judge-facing docs vs the measured records (Oct 26, 2026)

Maximizer iteration 51. Deterministic audit (no API calls) of
the two documents a judge reads first -- SUBMISSION.md and
README.md -- against the measured records, run fresh at the
current repo state. Three stale current-status framings found
by this audit were fixed in the same iteration (below); dated
historical eval records were left unaltered.

## Checks (all recomputed fresh)

- Demo suite fresh: 24 tests run, green: True
- Full-bench summary recomputes from its per-run rows: True -- 12/12 passed, guardrail escalated True, growth +42, 433.47s, est. $0.3910 total / $0.0326 per passed issue
- demo_suite_fresh_24: True
- full_bench_summary_recomputes: True
- submission_carries_full_bench_figures: True
- submission_labels_split_era_cost: True
- submission_split_framing_current: True
- readme_tooling_row_current: True
- readme_baseline_current: True

## Stale framings fixed this iteration

- README.md run-the-baselines block said the demo suite was
  "6 passing" -- a pre-expansion leftover; the demo repo has
  been 24 tests since iteration 37. It now states 24 passing
  and that none of the 12 seeded defects is covered by a
  baseline test.
- SUBMISSION.md's Tooling section said a split experiment
  "keeps the split" in the present tense; the all-frontier
  supersession appeared paragraphs later. The paragraph now
  reads past tense with the supersession in the same
  paragraph, and README.md's META_AI_TOOLING row names the
  supersession too.
- SUBMISSION.md's Impact section quoted the $0.0254 per-issue
  cost without its configuration; it is now labeled a
  split-config measurement (the contest configuration's
  full-bench figure, $0.0326, is carried in the same draft).

## Verdict

All checks pass: True. The judge-facing
docs now state the current baseline, the current contest
configuration, and configuration-labeled costs wherever the
audited figures appear.

Honest limits: this audits the figures and framings listed
above, not every number ever written in the repo; dated
historical records keep their then-current wording by
design. Consistency verification, not model performance.
