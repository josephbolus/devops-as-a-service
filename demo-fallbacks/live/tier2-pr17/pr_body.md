## Add up to 3 retries with exponential backoff starting at 100ms to app/http_client.py get() for 5xx responses and network errors only.

Closes: Add retry with backoff to the HTTP client wrapper

### Plan
- Inspect app/http_client.py get() error handling and tests/test_baseline.py patterns
- Add retry loop to get() for 5xx and network errors: up to 3 retries with 100ms, 200ms, 400ms backoff, immediate HttpError on 4xx
- Add regression tests in new test file covering 5xx-then-success, persistent 5xx after 4 attempts, and 4xx after 1 attempt
- Run test suite to verify acceptance criteria and existing tests pass

### Files changed
- app/http_client.py
- tests/test_http_client_regression.py

### Tests
All tests pass (6 → 9 discovered).

### Reviewer
approve: Checked retry loop 4 attempts/3 retries, 100ms exponential backoff 0.1/0.2/0.4, 5xx retries with HttpError wrap, OSError retries with re-raise, 4xx single attempt no sleep; scope limited to app/http_client.py + tests/test_http_client_regression.py with no unrelated changes; tests 6->9 pass; regression covers 5xx-then-success, persistent 5xx exhaustion, 4xx no-retry; sleep mocked so no timing risk.

