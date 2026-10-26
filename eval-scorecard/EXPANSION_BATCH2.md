# Expansion batch 2 — issues #6/#7/#12 live, all-frontier (Oct 26, 2026)

Issue-expansion directive (Joseph, Oct 26): the seeded set grows
from 3 work issues toward 12 across researched DevOps/SRE families.
Batch 2 seeds three families into the demo codebase as genuine
pre-existing defects (baseline suite 18/18 passes with each bug
present; the defect case is uncovered, exactly like Tier 1):

- #6 database connections — `app/pool.py`: `ConnectionPool.run()`
  releases its connection only on the success path, leaking one
  connection per failure until the pool exhausts.
- #7 resource exhaustion (disk) — `app/logwriter.py`: `write()`
  never rotates at `max_bytes`, so the log file grows without
  bound until the disk fills.
- #12 scheduled jobs — `app/scheduler.py`: `run_once()` records a
  transient failure as a completed run and returns 'ran', so the
  job silently skips the day while reporting success.

## Measured pass (all-frontier contest configuration)

- connection-pool (#6 database connection-pool leak): **passed** — tests 18 -> 22, 26.49s, est. cost $0.0314 (char estimate at wonder prices $4/$20 per 1M)
- log-rotation (#7 resource exhaustion (disk / log rotation)): **passed** — tests 18 -> 21, 30.12s, est. cost $0.0349 (char estimate at wonder prices $4/$20 per 1M)
- scheduled-job (#12 scheduled job silently skips): **passed** — tests 18 -> 21, 21.48s, est. cost $0.0303 (char estimate at wonder prices $4/$20 per 1M)

Summary: issues passed 3/3; total test growth +10; total wall clock 78.09s; total est. cost $0.0966; est. cost per passed issue $0.0322.

Honest limits: one live pass per new issue (n=1 each) on the
seeded demo codebase; no repeatability claim for the expanded
set yet. Costs are character estimates, not provider-reported
usage. The demo video still showcases the original three tiers;
the expanded set is the evaluation bench behind it.
