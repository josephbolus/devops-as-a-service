# Spark-1.1 replicate — does iteration 29's pass repeat? (Oct 26, 2026)

Maximizer iteration 43. Iteration 29 ran the original three work tiers live with every role on `muse-spark-1.1` once and passed 3/3 + guardrail (growth +10, 77.67s). It was since then the last model in the Tooling record with only a single pipeline pass — spark-1.2 was replicated at iteration 30 and the all-frontier contest configuration at iteration 32. This file is the replicate: the identical model configuration run a second time, reported as measured, NOT re-run for a cleaner record.

Baseline caveat: iteration 29 ran at the pre-expansion 6-test demo baseline; this replicate runs at the current 24-test baseline (iterations 35–37), so tests_before is 24 below, not 6. Pass/fail and growth deltas are comparable across the passes; absolute test counts are not.

## Replicate pass (iteration 43, all roles muse-spark-1.1)

- tier1: **passed** — tests 24 → 29, 23.35s, est. cost $0.0054 (char estimate, spark-1.1 priced at spark-1.3 rates — see daas/cost.py unknown-model rule)
- tier2: **passed** — tests 24 → 29, 35.72s, est. cost $0.0131 (char estimate, spark-1.1 priced at spark-1.3 rates — see daas/cost.py unknown-model rule)
- tier3: **passed** — tests 24 → 27, 24.91s, est. cost $0.0075 (char estimate, spark-1.1 priced at spark-1.3 rates — see daas/cost.py unknown-model rule)
- guardrail: **escalated** — tests n/a, 0.0s, est. cost $0.0000 (char estimate, spark-1.1 priced at spark-1.3 rates — see daas/cost.py unknown-model rule)

Replicate summary: work tiers passed 3/3; guardrail escalated: True; total test growth +13; total wall clock 83.98s; total est. cost $0.0260.

## Two-pass comparison (spark-1.1, all roles)

- Iteration 29 pass: work tiers 3/3, growth +10, 77.67s, est. $0.0245, at the 6-test demo baseline (source: eval-scorecard/spark11-runs.json (maximizer iteration 29))
- Iteration 43 replicate: work tiers 3/3, growth +13, 83.98s, est. $0.0260, at the 24-test demo baseline
- Combined: growth each [10, 13], mean +11.5, range +10 to +13; guardrail escalated on both passes: True.

Verdict (computed from the two measured passes): The replicate repeats iteration 29's outcome exactly at the outcome level — 3/3 work tiers passed and the guardrail escalated — so spark-1.1's single-pass status is removed: every probed Meta model now has at least two live pipeline passes. Growth deltas across the two passes are stated above as measured; the baseline change (6 → 24 tests) means the absolute counts are not compared.

Honest limits: this is the second pass of one non-contest configuration on the original three seeded tiers (n=3 issues). The contest configuration remains all-frontier (every role muse-wonder-1.0, spark only as availability fallback, per Joseph's Oct 26 directive); neither spark-1.1 pass re-decides it. No tool calling or responses-endpoint surface is claimed — the connector helper offers chat completions only. Costs are character estimates, not provider-reported usage.
