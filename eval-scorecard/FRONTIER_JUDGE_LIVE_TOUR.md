# Frontier Judge Mode — live tour under the contest configuration

Measured Oct 26, 2026 (maximizer iteration 34) by
`hackathon-agent-scaffold/run_frontier_judge_live_tour.py`: the demo
console's one-click `POST /api/judge/run` endpoint was exercised
over real HTTP in **live** mode for **every** seeded issue — no
operator choices after each click, real Meta Model API calls
through the custom.meta-model-api connector under the all-frontier
contest configuration (every role `muse-wonder-1.0`; `muse-spark-1.3`
configured only as availability fallback). Each stop's closing results
card is recorded in `frontier-judge-live-tour.json`.

| Issue | Mode | Overall | Tests | Delta | Captions | Elapsed | Card cost (est.) |
|---|---|---|---|---|---|---|---|
| tier1 | live | pass | 6 → 8 | +2 | 9 | 16.20s | $0.0150 |
| tier2 | live | pass | 6 → 12 | +6 | 9 | 96.34s | $0.0656 |
| tier3 | live | pass | 6 → 8 | +2 | 9 | 21.66s | $0.0297 |
| guardrail | live | escalated | — | — | 1 | 0.02s | $0.0000 |

Work issues passed 3/3 with a combined test-count delta of +10; the guardrail issue ended escalated, as its card must report — never as a pass. Combined card cost est. $0.1103 (char-count estimates at wonder prices, not billing data).

## Comparison with the split-config live tour (iteration 21)

- Split tour (source: eval-scorecard/judge-live-tour.json (maximizer iteration 21, kept split config)): work passed 2/3, combined delta +11, guardrail escalated: True, combined card cost est. $0.0342, total elapsed 164.72s — that tour's Tier 2 stop was lost to a provider HTTP 503 on the reviewer call.
- All-frontier tour (this run): work passed 3/3, combined delta +10, guardrail escalated: True, combined card cost est. $0.1103, total elapsed 134.23s. Every work stop's card records `muse-wonder-1.0` on every role that ran (char estimates at wonder prices are higher than the split's mixed prices — stated, not hidden).

## What this proves — and what it does not

- Proves: the self-guided path is live-proven at every tour stop under the configuration that will actually be judged. A judge's single click per stop drives the real pipeline — guardrail, triage, plan, code, tests, review — and the narration captions and results cards describe the live runs that actually happened, including measured costs, timings, and the frontier model on each card. A stop that does not pass is reported by its card as measured, never dressed up as a pass.
- One live tour of the seeded set through the console path; the broader live evidence remains the timed runs, the frontier repeatability record, and the generalization runs in `SCORECARD.md` and PRs #16/#17/#18. This tour opens no PR (Judge Mode live runs against a throwaway copy unless a real PR is explicitly requested).
- It is not the demo video. Nothing is recorded; Joseph's Thu Oct 29, 2026 recording remains the Demo criterion's human-owned item (Nov 2 morning is emergency-retake only).
