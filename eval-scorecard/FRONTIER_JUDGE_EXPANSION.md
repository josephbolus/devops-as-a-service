# Frontier Judge Mode — live tour of the nine expansion issues

Measured Oct 26, 2026 (maximizer iteration 41) by
`hackathon-agent-scaffold/run_frontier_judge_expansion_eval.py`: the demo console's one-click `POST /api/judge/run` endpoint was exercised over real HTTP in **live** mode for **all nine** expansion issues at the current 24-test baseline — no operator choices after each click, real Meta Model API calls through the custom.meta-model-api connector under the all-frontier contest configuration (every role `muse-wonder-1.0`; `muse-spark-1.3` configured only as availability fallback). Before this iteration the console catalog exposed only the original four issues; the expansion issues are now in `demo_ui.ISSUE_CATALOG`, labeled live-only (MockClient has no canned answers for them). Each stop's closing results card is recorded in `frontier-judge-expansion.json`.

| Issue | Mode | Overall | Tests | Delta | Captions | Elapsed | Card cost (est.) |
|---|---|---|---|---|---|---|---|
| config_drift | live | pass | 24 → 28 | +4 | 9 | 25.12s | $0.0254 |
| health_check | live | pass | 24 → 28 | +4 | 9 | 39.48s | $0.0319 |
| alert_threshold | live | pass | 24 → 27 | +3 | 9 | 15.61s | $0.0179 |
| connection_pool | live | pass | 24 → 29 | +5 | 9 | 19.32s | $0.0346 |
| log_rotation | live | pass | 24 → 27 | +3 | 9 | 41.39s | $0.0444 |
| scheduled_job | live | pass | 24 → 28 | +4 | 9 | 21.23s | $0.0360 |
| retry_storm | live | pass | 24 → 27 | +3 | 9 | 25.99s | $0.0334 |
| deploy_token | live | pass | 24 → 27 | +3 | 9 | 23.45s | $0.0299 |
| api_pagination | live | pass | 24 → 27 | +3 | 9 | 19.93s | $0.0252 |

Work issues passed 9/9 with a combined test-count delta of +32. Combined card cost est. $0.2787 (char-count estimates at wonder prices, not billing data).

## Comparison with the direct-pipeline expansion record

- Prior direct runs (source: eval-scorecard/expansion-batch{1,2,3}-runs.json (maximizer iterations 35-37, direct pipeline.run, all-frontier)): issues passed 9/9, combined test growth +32, combined cost est. $0.2666, total wall clock 211.80s — those runs called pipeline.run directly, not through the console.
- Judge Mode tour (this run): work passed 9/9, combined delta +32, combined card cost est. $0.2787, total elapsed 231.51s. Every work stop's card records `muse-wonder-1.0` on every role that ran (char estimates at wonder prices; tests_before on every stop is the current 24-test baseline).

## What this proves — and what it does not

- Proves: the self-guided Judge Mode path now covers the full 12-work-issue seeded set, not only the original three tiers — a judge can run every expansion scenario unaided through the console, and the narration captions and results cards describe the live runs that actually happened. A stop that does not pass is reported by its card as measured, never dressed up as a pass.
- One live tour of the expansion issues through the console path; the broader live evidence remains the direct expansion records, the timed runs, and PRs #16/#17/#18. This tour opens no PR (Judge Mode live runs against a throwaway copy).
- It is not the demo video. Nothing is recorded; Joseph's Thu Oct 29, 2026 recording remains the Demo criterion's human-owned item (Nov 2 morning is emergency-retake only).
