# Model fallback — live validation (Oct 26, 2026)

Maximizer iteration 28. Until this iteration only two Meta models had ever served a production role (`muse-spark-1.3`, `muse-wonder-1.0`) and a model-level failure had no recourse. Both live clients in `daas/llm.py` now accept a fallback model (`DAAS_FALLBACK_MODEL` / `DAAS_FALLBACK_<ROLE>`), used only on model-availability failures (HTTP 404 / `model_not_found`) or after transient retries are exhausted — never on auth or other 4xx — and record `fallback_stats`. Unit proof against mocked transports: `tests/test_model_fallback.py`. This file is the live record.

## Model probes (tiny JSON completion through the connector)

- muse-spark-1.3: ok (2.39s)
- muse-wonder-1.0: ok (1.73s)
- muse-spark-1.2: ok (1.69s)
- muse-spark-1.1: ok (1.08s)

## Live fallback exercise (controlled probe)

- Primary model (deliberately invalid): muse-spark-0.0-does-not-exist
- Fallback model: muse-spark-1.2
- Outcome: **ok** in 2.95s
- retry_stats: {'calls': 2, 'retries': 0, 'transient_failures': 0}
- fallback_stats: {'fallbacks': 1, 'fallback_successes': 1}

The provider answered the invalid primary with a real HTTP 404 `model_not_found`; the client fell back once and the fallback model answered. This is a controlled probe of the fallback path, not a claim that a shipped configuration failed live.

## Full seeded set on the fallback model (all roles muse-spark-1.2)

- tier1: **passed** — tests 6 → 13, 22.63s, est. cost $0.0074 (char estimate, spark-1.2 priced at spark-1.3 rates — see daas/cost.py unknown-model rule)
- tier2: **passed** — tests 6 → 14, 34.31s, est. cost $0.0149 (char estimate, spark-1.2 priced at spark-1.3 rates — see daas/cost.py unknown-model rule)
- tier3: **passed** — tests 6 → 11, 31.65s, est. cost $0.0085 (char estimate, spark-1.2 priced at spark-1.3 rates — see daas/cost.py unknown-model rule)
- guardrail: **escalated** — tests n/a, 0.0s, est. cost $0.0000 (char estimate, spark-1.2 priced at spark-1.3 rates — see daas/cost.py unknown-model rule)

Summary: probes 4/4 ok; fallback exercise ok (fallback_stats {'fallbacks': 1, 'fallback_successes': 1}); work tiers passed 3/3; guardrail escalated: True; total test growth +20; total wall clock 88.59s; total est. cost $0.0309.

Honest limits: muse-spark-1.2 is now proven live in all four production roles on the seeded set (one pass) and muse-spark-1.1 is probe-proven only — no pipeline run on 1.1 is claimed. The kept live configuration remains the measured split (CODER/REVIEWER muse-wonder-1.0, TRIAGE/PLANNER muse-spark-1.3); this iteration proves a fallback, it does not re-decide the split. No tool calling or responses-endpoint surface is claimed — the connector helper offers chat completions only.
