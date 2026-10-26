# Provider-transient retry — live validation (Oct 25, 2026)

Maximizer iteration 22. Motivation: the Judge Mode live tour (`JUDGE_LIVE_TOUR.md`) lost Tier 2 when its reviewer call failed with a provider HTTP 503 (`service_overloaded`) and the client raised immediately; its tests stage had already passed 6 → 11.

Fix: both live clients in `daas/llm.py` retry transient failures only (HTTP 429/500/502/503/504, overload/rate-limit/timeout markers) with exponential backoff, `max_attempts=3`; auth and other 4xx failures are never retried. Recovery after simulated 503s is pinned by `tests/test_retry.py`. This file records ONE live validation run of the Tier 2 issue under the retrying client — it does not replace or erase the tour's 503 record.

- Outcome: **passed**
- Tests: 6 → 10 (+4)
- Wall clock: 105.41s
- Model calls (pipeline level): 4
- retry_stats: calls=4, retries=0, transient_failures=0
- Reviewer verdict: approve
- Est. API cost: $0.0470 (char estimate)

Honest limits: the retry logic is proven against simulated 503s in the test suite. This live run proves the Tier 2 issue passes end to end under the retrying client; a retry is claimed live only if `retries` above is greater than zero — zero means the provider did not blip during this run. One run of one seeded issue; the tour record stands as measured.
