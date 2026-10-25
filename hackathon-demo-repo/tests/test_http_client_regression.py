import unittest
from unittest.mock import call, patch
import urllib.error

from app.http_client import HttpError, get


class FakeResponse:
    def __init__(self, body=b"ok"):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


def make_http_error(code):
    return urllib.error.HTTPError("http://example.com/", code, f"HTTP {code}", {}, None)


class TestHttpClientRetry(unittest.TestCase):
    def test_5xx_then_success_returns_body(self):
        err = make_http_error(500)
        calls = []

        def opener(url):
            calls.append(url)
            if len(calls) == 1:
                raise err
            return FakeResponse(b"hello")

        with patch("app.http_client.time.sleep") as mock_sleep:
            result = get("http://example.com/", opener=opener)
        self.assertEqual(result, "hello")
        self.assertEqual(len(calls), 2)
        mock_sleep.assert_called_once_with(0.1)

    def test_persistent_5xx_raises_after_4_attempts(self):
        calls = []

        def opener(url):
            calls.append(url)
            raise make_http_error(503)

        with patch("app.http_client.time.sleep") as mock_sleep:
            with self.assertRaises(HttpError):
                get("http://example.com/", opener=opener)
        self.assertEqual(len(calls), 4)
        self.assertEqual(mock_sleep.call_args_list, [call(0.1), call(0.2), call(0.4)])

    def test_4xx_raises_after_single_attempt(self):
        calls = []

        def opener(url):
            calls.append(url)
            raise make_http_error(404)

        with patch("app.http_client.time.sleep") as mock_sleep:
            with self.assertRaises(HttpError) as ctx:
                get("http://example.com/", opener=opener)
        self.assertEqual(ctx.exception.status, 404)
        self.assertEqual(len(calls), 1)
        mock_sleep.assert_not_called()
