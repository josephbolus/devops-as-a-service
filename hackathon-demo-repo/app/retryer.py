"""Retry helper for calls to an upstream dependency.

Expansion seed issue #5 (cascading failure / retry storm, intentional
— do not fix in the scaffold): when the upstream hiccups, callers
retry immediately in a tight loop with no delay at all, so a fleet of
clients hammers the struggling upstream in lockstep and turns a brief
hiccup into a cascading outage. A backoff helper exists and is
correct, but the retry loop never uses it.
"""
import time


def backoff_delay(attempt, base=0.1):
    """Delay before retry number `attempt` (0-indexed): base * 2**attempt."""
    return base * (2 ** attempt)


def call_with_retry(fn, max_attempts=3, sleep=None):
    """Call fn(), retrying on exception with exponential backoff.

    Up to `max_attempts` total attempts. Before retry number n
    (0-indexed) the caller sleeps backoff_delay(n) seconds via
    `sleep` (time.sleep by default; injectable for tests). The last
    attempt's exception propagates unchanged. A first-try success
    sleeps never.
    """
    sleep = time.sleep if sleep is None else sleep
    last = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - retry any failure
            last = e
            # BUG: retries immediately — sleep/backoff_delay are never
            # used, so retries storm the upstream with zero delay.
    raise last
