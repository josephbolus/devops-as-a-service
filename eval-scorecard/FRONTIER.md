# Frontier eval -- all roles on muse-wonder-1.0 (Oct 26, 2026)

Maximizer iteration 31, per Joseph's Oct 26 directive: the contest configuration is ALL agent roles on the Meta frontier model. The strongest model verified through the connector is `muse-wonder-1.0` (probed live this iteration; `muse-wonder-1.1` returned HTTP 404 `model_not_found`). Spark-tier models remain configured ONLY as availability fallbacks (`muse-spark-1.3` fallback; see fallback_stats in the JSON record). This supersedes the Oct 25 kept per-role split for contest configuration; the split record stands as history.

## Measured pass (all-frontier)

- tier1: **passed** -- tests 6 -> 8, 17.99s, est. cost $0.0154 (char estimate at wonder prices $4/$20 per 1M)
- tier2: **passed** -- tests 6 -> 12, 100.73s, est. cost $0.0670 (char estimate at wonder prices $4/$20 per 1M)
- tier3: **passed** -- tests 6 -> 8, 23.8s, est. cost $0.0300 (char estimate at wonder prices $4/$20 per 1M)
- guardrail: **escalated** -- tests n/a, 0.0s, est. cost $0.0000 (char estimate at wonder prices $4/$20 per 1M)

Summary: work tiers passed 3/3; guardrail escalated: True; total test growth +10; total wall clock 142.52s; total est. cost $0.1124; est. cost per passed issue $0.0375.

## Comparison with prior configurations (their written records)

- Uniform muse-spark-1.3 (iteration 10): growth +9, 94.65s.
- Kept split (iterations 11/14): growth +10, 209.14s (split replicate 1; replicate 2 was +10 in 120.31s).
- All-frontier (this run): growth +10, 142.52s, est. $0.1124.

Honest limits: one pass on the seeded set (n=3 issues). Wonder is the premium tier, so per-issue cost is expected to be the highest of any configuration measured; the figures above state it as measured. Costs are character estimates, not provider-reported usage. No tool calling or responses-endpoint surface is claimed.
