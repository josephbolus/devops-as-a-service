# Judge Mode tour — all four seeded issues, self-guided

Measured Oct 25, 2026 (maximizer iteration 18) by
`hackathon-agent-scaffold/run_judge_tour.py`: the demo console's
one-click `POST /api/judge/run` endpoint was exercised over real
HTTP for **every** seeded issue in mock mode (the unattended-judge
default), with no operator choices after the click. Each stop's
closing results card is recorded in `judge-tour.json`.

| Issue | Overall | Tests | Delta | Captions | Card cost (est.) |
|---|---|---|---|---|---|
| tier1 | pass | 6 → 7 | +1 | 7 | $0.0000 |
| tier2 | pass | 6 → 9 | +3 | 7 | $0.0000 |
| tier3 | pass | 6 → 8 | +2 | 7 | $0.0000 |
| guardrail | escalated | — | — | 1 | $0.0000 |

Work issues passed 3/3 with a combined test-count delta of +6; the guardrail issue ended escalated, its later stages pending, exactly as its card must report — never as a pass.

## What this proves — and what it does not

- Proves: Judge Mode is not a Tier-1-only path. All four tour stops run unaided, every event carries a narration caption derived from that event, and every stop ends in a results card whose overall outcome, per-stage statuses, and test delta match the run that actually happened.
- Mock mode is plumbing proof, not model performance. The live evidence remains the timed live runs and PRs #16/#17/#18 in `SCORECARD.md`; this tour makes that evidence reachable by a judge without an operator, it does not replace it.
- It is not the demo video. Nothing is recorded; Joseph's Nov 2 recording remains the Demo criterion's human-owned item.
