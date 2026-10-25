# Judge Mode — live run, self-guided

Measured Oct 25, 2026 (maximizer iteration 20) by
`hackathon-agent-scaffold/run_judge_live.py`: the demo console's
one-click `POST /api/judge/run` endpoint was exercised over real
HTTP in **live** mode — the Tier 1 seeded issue, no operator
choices after the click, real Meta Model API calls through the
custom.meta-model-api connector under the kept split config
(CODER/REVIEWER=muse-wonder-1.0, TRIAGE/PLANNER=muse-spark-1.3).
The closing results card is recorded in `judge-live.json`.

| Issue | Mode | Overall | Tests | Delta | Captions | Elapsed | Card cost (est.) |
|---|---|---|---|---|---|---|---|
| tier1 | live | pass | 6 → 9 | +3 | 7 | 20.44s | $0.0108 |

Outcome: overall **pass** — every stage in the closing card reports pass, 7 event-derived narration captions fired, and the card's per-role cost summary records the split models on the calls that actually ran (char-count estimate, not billing data).

## What this proves — and what it does not

- Proves: the self-guided path is not mock-only. A judge's single click drives the real pipeline — guardrail, triage, plan, code, tests, review — and the narration captions and results card describe the live run that actually happened, including its measured cost and timings.
- One live run of one seeded issue through the console path; the broader live evidence remains the timed runs, repeatability record, and generalization runs in `SCORECARD.md` and PRs #16/#17/#18. This run opens no PR (Judge Mode live runs against a throwaway copy unless a real PR is explicitly requested).
- It is not the demo video. Nothing is recorded; Joseph's Nov 2 recording remains the Demo criterion's human-owned item.
