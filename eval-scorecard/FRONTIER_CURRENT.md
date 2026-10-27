# Frontier current-baseline -- original tiers, direct pipeline, at 24 tests (Oct 26, 2026)

Maximizer iteration 48. The all-frontier contest
configuration's direct-pipeline record for the original
seeded set (iterations 31/32: two passes, 3/3 + guardrail
each, growth +10/+9) was measured at the pre-expansion
6-test demo baseline. The demo repo has since tripled to
24 tests (expansion seeding, iterations 35-37), and every
other measured shape has been re-proven at the current
baseline (expansion direct replicate iteration 44, Judge
Mode tours iterations 40/41, spark-1.1 iteration 43,
human gate iteration 47). This file is the original tiers'
direct-pipeline pass at the current baseline: Tier 1/2/3 +
guardrail run once each under the identical contest
configuration, reported as measured and NOT re-run for a
cleaner record. Growth deltas are the quantity comparable
across the baseline change; absolute counts carry that
caveat.

## Current-baseline pass (iteration 48, all roles muse-wonder-1.0)

- tier1: **passed** -- tests 24 -> 26, 20.72s, est. cost $0.0156 (char estimate at wonder prices $4/$20 per 1M)
- tier2: **passed** -- tests 24 -> 28, 108.26s, est. cost $0.0617 (char estimate at wonder prices $4/$20 per 1M)
- tier3: **passed** -- tests 24 -> 26, 22.93s, est. cost $0.0274 (char estimate at wonder prices $4/$20 per 1M)
- guardrail: **escalated** -- tests n/a, 0.0s, est. cost $0.0000 (char estimate at wonder prices $4/$20 per 1M)

Pass summary: work tiers passed 3/3; guardrail escalated: True; total test growth +8; total wall clock 151.91s; total est. cost $0.1047; est. cost per passed issue $0.0349.

## Three-pass comparison (all-frontier, direct pipeline)

- iteration 31 pass (6-test baseline): work tiers 3/3, growth +10, 142.52s, est. $0.1124 (source: eval-scorecard/frontier-runs.json)
- iteration 32 pass (6-test baseline): work tiers 3/3, growth +9, 171.57s, est. $0.1112 (source: eval-scorecard/frontier-replicate-runs.json)
- Iteration 48 pass (24-test baseline): work tiers 3/3, growth +8, 151.91s, est. $0.1047
- Combined: work tiers each ['3/3', '3/3', '3/3']; growth each [10, 9, 8], mean +9.0, range +8 to +10; guardrail escalated on all passes: True.

Verdict (computed from the three measured passes): The contest configuration's direct record now holds at the baseline judges will actually see: three direct passes, 3/3 work tiers and a guardrail escalation on each, the third at the current 24-test baseline -- the original tiers' direct record is no longer stale-baseline. Growth still varies pass to pass (see above).

Honest limits: three direct passes of the original tiers
on the seeded demo codebase (the first two at the 6-test
baseline, this one at 24); no real users or real backlog,
and review time is still the impact model's 10-minute
assumption. This pass goes through pipeline.run directly,
not the demo console (the console path at this baseline
is iteration 40's record). Costs are character estimates,
not provider-reported usage.
