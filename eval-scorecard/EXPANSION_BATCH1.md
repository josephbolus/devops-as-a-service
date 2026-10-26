# Expansion batch 1 — issues #4/#8/#9 live, all-frontier (Oct 26, 2026)

Issue-expansion directive (Joseph, Oct 26): the seeded set grows
from 3 work issues toward 12 across researched DevOps/SRE families.
Batch 1 seeds three families into the demo codebase as genuine
pre-existing defects (baseline suite 12/12 passes with each bug
present; the defect case is uncovered, exactly like Tier 1):

- #4 configuration drift — `app/config.py`: `load_config()` spreads
  `DEFAULTS` last, silently discarding `APP_*` env overrides.
- #8 health-check correctness — `app/health.py`: `overall_status()`
  is healthy if ANY check is ok, so a down critical dependency
  still returns 200 to the load balancer.
- #9 alerting defect — `app/alerts.py`: `should_page()` compares
  with `<`, paging on healthy values and silent above threshold.

## Measured pass (all-frontier contest configuration)

- config-drift (#4 configuration drift): **passed** — tests 12 -> 17, 17.8s, est. cost $0.0293 (char estimate at wonder prices $4/$20 per 1M)
- health-check (#8 health-check correctness): **passed** — tests 12 -> 16, 28.83s, est. cost $0.0296 (char estimate at wonder prices $4/$20 per 1M)
- alert-threshold (#9 alerting defect): **passed** — tests 12 -> 15, 14.22s, est. cost $0.0187 (char estimate at wonder prices $4/$20 per 1M)

Summary: issues passed 3/3; total test growth +12; total wall clock 60.85s; total est. cost $0.0776; est. cost per passed issue $0.0259.

Honest limits: one live pass per new issue (n=1 each) on the
seeded demo codebase; no repeatability claim for the expanded
set yet. Costs are character estimates, not provider-reported
usage. The demo video still showcases the original three tiers;
the expanded set is the evaluation bench behind it.
