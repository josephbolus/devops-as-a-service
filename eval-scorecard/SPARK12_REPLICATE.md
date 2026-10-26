# Spark-1.2 replicate — was the +20 growth signal or variance? (Oct 26, 2026)

Maximizer iteration 30. Iteration 28 ran the full seeded set live with every role on `muse-spark-1.2` once and recorded total test growth +20 — roughly double the +9/+10 growth of the uniform, split, and spark-1.1 configurations — and both iterations 28 and 29 stated that single pass does not re-decide the kept split. This file is the replicate: the identical configuration run a second time, reported as measured.

## Replicate pass (iteration 30, all roles muse-spark-1.2)

- tier1: **passed** — tests 6 → 11, 24.6s, est. cost $0.0051 (char estimate, spark-1.2 priced at spark-1.3 rates — see daas/cost.py unknown-model rule)
- tier2: **passed** — tests 6 → 10, 48.57s, est. cost $0.0109 (char estimate, spark-1.2 priced at spark-1.3 rates — see daas/cost.py unknown-model rule)
- tier3: **passed** — tests 6 → 11, 41.57s, est. cost $0.0102 (char estimate, spark-1.2 priced at spark-1.3 rates — see daas/cost.py unknown-model rule)
- guardrail: **escalated** — tests n/a, 0.0s, est. cost $0.0000 (char estimate, spark-1.2 priced at spark-1.3 rates — see daas/cost.py unknown-model rule)

Replicate summary: work tiers passed 3/3; guardrail escalated: True; total test growth +14; total wall clock 114.74s; total est. cost $0.0262.

## Two-pass comparison (spark-1.2, all roles)

- Iteration 28 pass: work tiers 3/3, growth +20, 88.59s, est. $0.0309 (source: eval-scorecard/model-fallback-runs.json (maximizer iteration 28))
- Iteration 30 replicate: work tiers 3/3, growth +14, 114.74s, est. $0.0262
- Combined: growth each [20, 14], mean +17.0, range +14 to +20; guardrail escalated on both passes: True.

Verdict (computed from the two measured growths): The replicate growth sits between the typical +9/+10 of the other configurations and the original +20, so the original figure is only partly repeated: spark-1.2 may grow tests somewhat more, but +20 itself looks like the high end of variance at this sample size.

Honest limits: this is the second pass of one alternate configuration on the seeded set (n=3 issues, now 2 attempts under spark-1.2). The kept live configuration remains the measured split (CODER/REVIEWER muse-wonder-1.0, TRIAGE/PLANNER muse-spark-1.3); neither pass re-decides it, and test growth is a secondary signal — pass counts tied at 3/3 + guardrail in both spark-1.2 passes if the replicate also passed, which the rows above state as measured. No tool calling or responses-endpoint surface is claimed — the connector helper offers chat completions only. Costs are character estimates, not provider-reported usage.
