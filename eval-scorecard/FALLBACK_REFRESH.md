# Demo fallback refresh — Oct 26, 2026 (maximizer iteration 42)

The recording-day fallback package (`demo-fallbacks/`) was generated
Oct 25 at the pre-expansion 6-test demo baseline. Iterations 35–37
tripled the demo repo to 24 tests, and iterations 26–27 added the
regression and issue-target gates — so the checked-in mock end states
a judge or the Oct 29 recording would walk no longer matched the
system: they showed 6-test counts and PR bodies with no gate sections,
and the package README still said "Nov 2 recording".

## What was done

- Regenerated the mock half with `generate_demo_fallbacks.py`
  (deterministic MockClient, offline, no API calls; the live half
  under `demo-fallbacks/live/` is never touched by the generator and
  stands unaltered as the Oct 25 capture at the then-current
  baseline). Regeneration is byte-identical on re-run (manifest md5
  verified across two runs).
- Refreshed results, as generated: Tier 1 passed 24 → 25, Tier 2
  passed 24 → 27, Tier 3 passed 24 → 26, guardrail escalated with
  zero model calls; no unexpected files in any run. The refreshed PR
  bodies now carry the Regression gate and Issue-target gate
  sections the current pipeline emits, and each mock tier now
  includes its `cost.json` (method `mock_no_api_call`, $0.00).
- `demo-fallbacks/README.md` and the `DEMO_RUN_OF_SHOW.md` pre-flight
  now state the current counts and the Thu Oct 29, 2026 recording
  date; the stale "Nov 2 recording" references in the root and
  scaffold READMEs were corrected to Oct 29 (Nov 2 morning remains
  emergency-retake only). Historical Oct 25 rehearsal rows in the
  run-of-show keep their original 6-test counts, labeled as the
  pre-expansion baseline they were measured at.

## What this does not prove

This is a mock-mode packaging refresh — plumbing and consistency
evidence, not model performance. No live run was made, no PR was
opened, and nothing was recorded: Joseph's Thu Oct 29 recording
remains the demo's binding gap.
