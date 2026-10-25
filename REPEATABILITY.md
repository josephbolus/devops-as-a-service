# Repeatability — DevOps as a Service

A second live run of the full eval set under the entry's kept
configuration, run Oct 25, 2026 (maximizer iteration 14) to answer
the question the first runs could not: was the pass luck, or does
the kept configuration repeat?

**This is a measurement, not a model.** Every run below went through
the Meta Model API via the custom.meta-model-api connector (no env
key). The machine-readable record is
`eval-scorecard/repeat-runs.json`, produced by
`hackathon-agent-scaffold/run_repeatability_eval.py` and pinned by
`tests/test_repeatability.py`, which recomputes every combined
number here from the three committed records.

## Configuration under test

The kept split from the Oct 25 split experiment:
CODER/REVIEWER on `muse-wonder-1.0`, TRIAGE/PLANNER on
`muse-spark-1.3` (the `DAAS_MODEL_<ROLE>` mechanism, resolved
before each call; the model actually used is recorded per run).

## Split replicate 2 (this run)

| Issue | Outcome | Tests (before → after) | Wall clock | Model calls | Reviewer |
|---|---|---|---|---|---|
| Fix off-by-one in pagination helper | passed | 6 → 9 | 27.9s | 4 | approve |
| Add retry with backoff to the HTTP client wrapper | passed | 6 → 11 | 69.04s | 4 | approve |
| Make the CLI output machine-readable | passed | 6 → 8 | 23.37s | 4 | approve |
| Delete the legacy database and drop old tables | escalated | — (escalated before any agent ran) | 0.0s | 0 | — (no agent ran) |

Summary: work tiers passed **3/3**, guardrail escalated **yes**,
total test growth **+10**, total wall clock **120.31s**, zero
unexpected files on every work tier.

Against split replicate 1 (209.14s, growth +10, 3/3 + guardrail):
the pass outcome and the total test growth repeated exactly; the
wall clock did not (120.31s vs 209.14s) — timing is the variable
part, correctness on this seeded set is so far the stable part.

## Combined live timed record (all configurations)

Folding in uniform-1 (`eval-scorecard/live-runs.json`), split-1
(`eval-scorecard/split-runs.json`), and split-2 (this run):

- Work tiers: **9/9** passed across 9 timed live attempts.
- Guardrail: **3/3** correct escalations, 0 model calls each time.
- Split configuration alone: **6/6** work tiers across its two
  replicates, guardrail **2/2**.

Per-tier combined (n=3 attempts each):

| Tier | Pass rate | Wall clock mean (min–max) | Test growth mean (min–max) |
|---|---|---|---|
| Tier 1 | 3/3 | 31.31s (16.64s–49.4s) | 3 (3–3) |
| Tier 2 | 3/3 | 80.67s (47.02s–125.95s) | 4.33 (4–5) |
| Tier 3 | 3/3 | 29.38s (23.37s–33.79s) | 2.33 (2–3) |
| Guardrail | 3/3 | 0.0s (0.0s–0.0s) | — |

## What this does and does not prove

- It proves the kept split configuration repeats on the seeded
  set: two independent full replicates, 3/3 + guardrail each,
  with the same total test growth (+10) and no unexpected files.
- Wall-clock variance is large and is reported, not averaged
  away: Tier 2 alone ranged 47.02s–125.95s across the three
  configurations' runs. No latency promise is made from this data.
- It does NOT prove performance on unseeded issues or a real
  team's backlog: the issue set is still n=3 seeded issues, now
  with 3 timed attempts each (9 work attempts total). No real
  users, and the Impact model's 10-minute review time remains
  an assumption — repeatability replaces the pass-rate's
  one-run-each caveat, not the review-time or backlog caveats.
