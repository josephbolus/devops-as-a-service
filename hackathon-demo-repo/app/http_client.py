"""Thin HTTP client wrapper.

Tier-2 seed issue (not yet implemented): transient 5xx responses and
network errors currently fail the job immediately. The issue asks for
up to 3 retries with exponential backoff (100ms base), 5xx/network
only, never 4xx.
"""

import urllib.request
import urllib.error


class HttpError(Exception):
    def __init__(self, status, message=""):
        super().__init__(message or f"HTTP {status}")
        self.status = status


def get(url, opener=None):
    """GET `url` and return the response body as text. Single attempt."""
    opener = opener or urllib.request.urlopen
    try:
        with opener(url) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, str(e)) from e
