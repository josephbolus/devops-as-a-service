## get() fails immediately on transient 5xx / network errors

Closes: Add retry with backoff to the HTTP client wrapper

### Plan
- Add a retry loop to get() in app/http_client.py (5xx/network only, never 4xx)
- Exponential backoff: 100ms, 200ms, 400ms between attempts
- Add tests for 5xx-then-success, persistent 5xx, and 4xx-no-retry

### Files changed
- app/http_client.py
- app/http_client.py
- tests/test_http_retry.py

### Tests
All tests pass (6 → 9 discovered).

### Reviewer
approve: Diff limited to expected files; regression test added.
