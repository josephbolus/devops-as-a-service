# Expansion batch 3 — issues #5/#10/#11 live, all-frontier (Oct 26, 2026)

Issue-expansion directive (Joseph, Oct 26): the seeded set grows
from 3 work issues toward 12 across researched DevOps/SRE families.
Batch 3 seeds the final three families into the demo codebase
as genuine pre-existing defects (baseline suite 24/24 passes
with each bug present; the defect case is uncovered, exactly
like Tier 1):

- #5 cascading failure / retry storm — `app/retryer.py`:
  `call_with_retry()` never sleeps between retries, so clients
  hammer a struggling upstream in a tight loop.
- #10 CI/CD + secrets — `app/deploy.py`: `run_deploy()` crashes
  with an unhandled RuntimeError on an expired token and prints
  the token itself in log lines and the error message.
- #11 dependency/API compatibility — `app/apiclient.py`:
  `fetch_all()` returns only the first page and ignores the
  upstream's `next_page` cursor, silently truncating the list.

## Measured pass (all-frontier contest configuration)

- retry-storm (#5 cascading failure / retry storm): **passed** — tests 24 -> 27, 23.35s, est. cost $0.0326 (char estimate at wonder prices $4/$20 per 1M)
- deploy-token (#10 CI/CD expired-token handling): **passed** — tests 24 -> 28, 24.07s, est. cost $0.0338 (char estimate at wonder prices $4/$20 per 1M)
- api-pagination (#11 upstream API pagination compatibility): **passed** — tests 24 -> 27, 25.44s, est. cost $0.0260 (char estimate at wonder prices $4/$20 per 1M)

Summary: issues passed 3/3; total test growth +10; total wall clock 72.86s; total est. cost $0.0924; est. cost per passed issue $0.0308.

Honest limits: one live pass per new issue (n=1 each) on the
seeded demo codebase; no repeatability claim for the expanded
set yet. With batch 3 the seeded work set reaches the spec's
12 issues. Costs are character estimates, not provider-reported
usage. The demo video still showcases the original three tiers;
the expanded set is the evaluation bench behind it.
