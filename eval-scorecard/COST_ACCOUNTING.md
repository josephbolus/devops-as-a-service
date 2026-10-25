# Per-run cost accounting — DevOps as a Service

What one fixed issue costs in Meta Model API calls, measured on live
runs on Oct 25, 2026 (maximizer new-feature backlog item 3). Machine
record: `cost-runs.json` next to this file, produced by
`hackathon-agent-scaffold/run_cost_eval.py`; the accounting code is
`hackathon-agent-scaffold/daas/cost.py`, wired into every pipeline
run (each result carries a `cost` summary and each run writes
`cost.json` next to its PR body), and the demo console's Judge Mode
results card surfaces the same summary per run. Pinned by
`tests/test_cost_accounting.py`, which recomputes every total here
from the per-call records.

## The honest headline: usage is not exposed, so these are estimates

Per-role token usage is **not exposed** to the pipeline on the path
every live run uses. The custom.meta-model-api connector helper
returns only the parsed reply content — the API response envelope,
including any `usage` field, never reaches this process — and the
direct client likewise reads only the reply content. So token counts
here are **estimates from character counts** (~4 chars/token, the
standard heuristic), and dollar figures are estimates computed from
those estimates at the published prices below. They are labeled
estimates in the record, the scorecard, the console, and this doc.
If a future transport surfaces real `usage`, `daas/cost.py` prefers
it (`method="api_usage"`) and nothing else changes.

Prices (USD per 1M tokens, standard tier): `muse-spark-1.3`
$1.25 input / $4.25 output (verified 2026-10-23, connector doc);
`muse-wonder-1.0` $4.00 input / $20.00 output (published Meta Model
API rates, cross-checked Oct 25, 2026). Configuration priced: the
kept split — CODER/REVIEWER on `muse-wonder-1.0`, TRIAGE/PLANNER
on `muse-spark-1.3`.

## Measured live runs (split config, fresh demo-repo copies)

| Issue | Outcome | Tests | Wall clock | Est. cost |
|---|---|---|---|---|
| Fix off-by-one in pagination helper | passed | 6 → 8 | 23.37s | $0.0101 |
| Add retry with backoff to the HTTP client wrapper | passed | 6 → 10 | 82.88s | $0.0469 |
| Make the CLI output machine-readable | passed | 6 → 8 | 36.27s | $0.0192 |
| Delete the legacy database and drop old tables | escalated | — | 0.0s | $0.0000 |

**Total est. cost: $0.0762** for the full set (3 work tiers +
guardrail). **Est. cost per passed issue: $0.0254.** The guardrail
run cost $0.00 — it escalates deterministically before any model
call, which is the cheapest safety property in the system.

Per-role totals across the three work runs (12 calls): CODER
$0.0550 (3 calls, Wonder), REVIEWER $0.0165 (3 calls, Wonder),
PLANNER $0.0031 (3 calls, Spark), TRIAGE $0.0017 (3 calls, Spark).
The Wonder-priced CODER dominates (~72% of the total) because it
emits the code — output tokens at $20/1M are the expensive unit in
this system, not input context.

## What this means against the impact model

`IMPACT_MODEL.md` counts **50 minutes of senior time saved per
passed issue** (60-minute manual floor − 10-minute review
assumption). At the measured estimate:

- **API cost per passed issue: $0.0254** (estimate).
- **API cost per senior-hour saved: $0.0305** — the per-issue cost
  divided by the 50 minutes (5/6 hour) the model says it buys back.

No wage rate is needed to read that: the API spend is three cents
per hour of senior time returned. Whether the split's premium is
worth it is the recorded trade from the split experiment — Wonder
costs ~4.7× Spark per output token, and the split was kept on test
growth (+10 vs +9), with its price recorded, not hidden.

## What this does NOT prove

- These are estimates, not billing records: character-count token
  estimates can drift from true tokenizer counts in either
  direction, and only the provider's invoice is exact.
- One pass over n=3 seeded issues: per-issue cost varies with the
  size of the fix the coder emits (Tier 2's larger edit cost ~4.6×
  Tier 1's run here), so a real backlog's average will differ.
- Mock runs cost $0 because no API call is made — that zero is
  real, and mock output is still never model-performance evidence.
