"""Thin HTTP client wrapper.

Tier-2 seed issue (not yet implemented): transient 5xx responses and
network errors currently fail the job immediately. The issue asks for
up to 3 retries with exponential backoff (100ms base), 5xx/network
only, never 4xx.
"""

import time
import urllib.request
import urllib.error


class HttpError(Exception):
    def __init__(self, status, message=""):
        super().__init__(message or f"HTTP {status}")
        self.status = status


def get(url, opener=None):
    """GET `url` and return the response body as text with retry."""
    opener = opener or urllib.request.urlopen
    delay = 0.1
    for attempt in range(4):
        try:
            with opener(url) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            code = getattr(e, "code", None)
            if code is not None and 500 <= code <= 599:
                if attempt >= 3:
                    raise HttpError(code, str(e)) from e
                time.sleep(delay)
                delay *= 2
                continue
            raise HttpError(code, str(e)) from e
        except OSError:
            if attempt >= 3:
                raise
            time.sleep(delay)
            delay *= 2
            continue
