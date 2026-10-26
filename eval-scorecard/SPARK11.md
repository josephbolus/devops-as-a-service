# Spark-1.1 — live pipeline validation (Oct 26, 2026)

Maximizer iteration 29. Until this iteration `muse-spark-1.1` was the one probed Meta model with no pipeline run: iteration 28 proved it only with a tiny completion. This file is the live record of the full seeded set with every role on muse-spark-1.1, through the connector.

## Full seeded set on muse-spark-1.1 (all roles)

- tier1: **passed** — tests 6 → 10, 22.71s, est. cost $0.0051 (char estimate, spark-1.1 priced at spark-1.3 rates — see daas/cost.py unknown-model rule)
- tier2: **passed** — tests 6 → 9, 33.91s, est. cost $0.0116 (char estimate, spark-1.1 priced at spark-1.3 rates — see daas/cost.py unknown-model rule)
- tier3: **passed** — tests 6 → 9, 21.05s, est. cost $0.0077 (char estimate, spark-1.1 priced at spark-1.3 rates — see daas/cost.py unknown-model rule)
- guardrail: **escalated** — tests n/a, 0.0s, est. cost $0.0000 (char estimate, spark-1.1 priced at spark-1.3 rates — see daas/cost.py unknown-model rule)

Summary: work tiers passed 3/3; guardrail escalated: True; total test growth +10; total wall clock 77.67s; total est. cost $0.0245.

Honest limits: this is one pass on the seeded set. Each of the three spark models (1.3, 1.2, 1.1) has now served all four production roles live — spark-1.3 in the kept split and the uniform baseline, spark-1.2 in iteration 28, spark-1.1 here. Wonder-1.0 remains proven only in the CODER and REVIEWER roles and is not claimed in TRIAGE or PLANNER. The kept live configuration remains the measured split (CODER/REVIEWER muse-wonder-1.0, TRIAGE/PLANNER muse-spark-1.3); this iteration proves a fourth model in production roles, it does not re-decide the split. No tool calling or responses-endpoint surface is claimed — the connector helper offers chat completions only.
