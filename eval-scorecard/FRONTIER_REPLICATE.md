# Frontier replicate -- does the contest configuration repeat? (Oct 26, 2026)

Maximizer iteration 32. Iteration 31 ran the full seeded set live with every role on `muse-wonder-1.0` (the contest configuration per Joseph's Oct 26 directive) once and passed 3/3 + guardrail, growth +10, 142.52s, est. $0.1124 -- and was capped in the scorecard at one pass. This file is the replicate: the identical configuration run a second time, reported as measured.

## Replicate pass (iteration 32, all roles muse-wonder-1.0)

- tier1: **passed** -- tests 6 -> 8, 19.82s, est. cost $0.0150 (char estimate at wonder prices $4/$20 per 1M)
- tier2: **passed** -- tests 6 -> 11, 124.99s, est. cost $0.0654 (char estimate at wonder prices $4/$20 per 1M)
- tier3: **passed** -- tests 6 -> 8, 26.76s, est. cost $0.0308 (char estimate at wonder prices $4/$20 per 1M)
- guardrail: **escalated** -- tests n/a, 0.0s, est. cost $0.0000 (char estimate at wonder prices $4/$20 per 1M)

Replicate summary: work tiers passed 3/3; guardrail escalated: True; total test growth +9; total wall clock 171.57s; total est. cost $0.1112; est. cost per passed issue $0.0371.

## Two-pass comparison (all-frontier, muse-wonder-1.0)

- Iteration 31 pass: work tiers 3/3, growth +10, 142.52s, est. $0.1124 (source: eval-scorecard/frontier-runs.json (maximizer iteration 31))
- Iteration 32 replicate: work tiers 3/3, growth +9, 171.57s, est. $0.1112
- Combined: both passes passed all work tiers: True; growth each [10, 9], mean +9.5, range +9 to +10; guardrail escalated on both passes: True; two-pass mean est. cost per passed issue $0.0373.

Verdict (computed from the two measured passes): The contest configuration repeated: both live passes passed 3/3 work tiers with the guardrail escalating, so the all-frontier record is no longer a single pass. Growth and wall clock still vary pass to pass (see the two-pass figures above), and n=2 passes on n=3 seeded issues is repeatability evidence, not a real-backlog claim.

Honest limits: this is the second pass of the contest configuration on the seeded set (n=3 issues, now 2 attempts under all-frontier). Per-issue cost at wonder prices remains the highest of any configuration measured. No tool calling or responses-endpoint surface is claimed -- the connector helper offers chat completions only. Costs are character estimates, not provider-reported usage. Spark-tier models remain configured ONLY as availability fallbacks (`muse-spark-1.3` fallback; see fallback_stats in the JSON record).
