# Frontier approve-and-resume — live human-gate flows (contest config)

Maximizer iteration 47 (Oct 26, 2026). The only prior live
approve-and-resume record (iteration 12, `resume-runs.json`)
ran under the kept split config at the pre-expansion 6-test
baseline. This eval re-runs the full human-gate flow set LIVE
under the all-frontier contest config (every role
muse-wonder-1.0, spark-1.3 fallback only, connector) at the
current 24-test demo baseline: guardrail escalation, the two
closing decisions, a still-destructive rescope, and a live
rescope to the Tier 1 issue. One attempt per flow, reported
as measured; nothing was re-run or tuned.

**Result: 5/5 flows handled as pre-registered.** The live rescope passed (tests 24 -> 26, 22.91s, est. $0.0163).

| Flow | Outcome | Model calls | Wall clock |
|---|---|---|---|
| escalation | escalated | 0 | 0.0s |
| reject | closed_rejected | 0 | 0.01s |
| handle_manually | closed_manual | 0 | 0.01s |
| rescope_still_destructive | re_escalated | 0 | 0.01s |
| rescope_live | passed | 4 | 22.91s |

## Honest limits

- One attempt per flow, on the seeded demo repo; the closing
  and re-escalation flows are deterministic (zero model calls
  by construction) -- the measured content is that they still
  behave that way through the live-configured client, and
  that the live rescope passes at the current baseline.
- Token counts are character-count estimates (the connector
  path does not expose API usage); costs are labeled estimates.
- The record is `frontier-resume-runs.json` beside this file;
  `tests/test_frontier_resume_eval.py` pins it.
