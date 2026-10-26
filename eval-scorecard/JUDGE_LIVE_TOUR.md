# Judge Mode — live tour, all four seeded issues self-guided

Measured Oct 25, 2026 (maximizer iteration 21) by
`hackathon-agent-scaffold/run_judge_live_tour.py`: the demo
console's one-click `POST /api/judge/run` endpoint was exercised
over real HTTP in **live** mode for **every** seeded issue — no
operator choices after each click, real Meta Model API calls
through the custom.meta-model-api connector under the kept split
config (CODER/REVIEWER=muse-wonder-1.0, TRIAGE/PLANNER=
muse-spark-1.3). Each stop's closing results card is recorded
in `judge-live-tour.json`.

| Issue | Mode | Overall | Tests | Delta | Captions | Elapsed | Card cost (est.) |
|---|---|---|---|---|---|---|---|
| tier1 | live | pass | 6 → 8 | +2 | 7 | 51.57s | $0.0112 |
| tier2 | live | fail | 6 → 11 | +5 | 5 | 69.90s | — |
| tier3 | live | pass | 6 → 10 | +4 | 7 | 43.24s | $0.0229 |
| guardrail | live | escalated | — | — | 1 | 0.02s | $0.0000 |

Work issues passed 2/3 with a combined test-count delta of +11; the guardrail issue ended escalated with zero model calls, exactly as its card must report — never as a pass. Combined card cost est. $0.0342 (char-count estimates, not billing data).

**tier2 did not complete** — reported as-is, not re-run for a cleaner record. Its tests stage passed (6 → 11) before the run errored: LLMError: Connector call failed: HTTP 503 from Meta Model API: {"error":{"code":"service_overloaded","message":"The backend is temporarily overloaded. Please retry.","param":null,"type":"server_error"}}

## What this proves — and what it does not

- Proves: the self-guided path is live-proven at every tour stop, not just Tier 1. A judge's single click per stop drives the real pipeline — guardrail, triage, plan, code, tests, review — and the narration captions and results cards describe the live runs that actually happened, including measured costs and timings and the split models on each card. Where a live run failed (a provider HTTP 503 on the reviewer call), the card reported fail/error with the review stage pending — it did not dress the failure up as a pass.
- One live tour of the seeded set through the console path; the broader live evidence remains the timed runs, repeatability record, and generalization runs in `SCORECARD.md` and PRs #16/#17/#18. This tour opens no PR (Judge Mode live runs against a throwaway copy unless a real PR is explicitly requested).
- It is not the demo video. Nothing is recorded; Joseph's Nov 2 recording remains the Demo criterion's human-owned item.
