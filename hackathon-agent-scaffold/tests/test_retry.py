"""Pin provider-transient retry (iteration 22).

Motivation is measured: the Judge Mode live tour (iteration 21) lost
Tier 2 when the REVIEWER call failed with provider HTTP 503
service_overloaded and the client raised immediately. These tests
prove, with mocked transports and NO live API call, that both live
clients retry transient failures with backoff, never retry auth /
non-transient failures, exhaust honestly, and record retry_stats.
"""
import io
import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))
from daas import prompts  # noqa: E402
from daas.llm import (  # noqa: E402
    ConnectorClient,
    LLMError,
    MetaModelClient,
    is_transient_error,
)

ROOT = Path(__file__).resolve().parents[2]


class TestTransientClassification(unittest.TestCase):
    def test_transient_codes_and_markers(self):
        self.assertTrue(is_transient_error("", code=503))
        self.assertTrue(is_transient_error("", code=429))
        self.assertTrue(is_transient_error("HTTP 503 from Meta Model API: service_overloaded"))
        self.assertTrue(is_transient_error("The backend is temporarily overloaded"))
        self.assertFalse(is_transient_error("", code=400))
        self.assertFalse(is_transient_error("", code=401))

    def test_auth_never_transient(self):
        self.assertFalse(is_transient_error("HTTP 401: invalid_api_key"))
        self.assertFalse(is_transient_error("invalid_api_key, try again later"))


class _Proc:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _connector_client(sleeps):
    with mock.patch.dict(os.environ, {}, clear=True):
        return ConnectorClient(max_attempts=3, backoff_base=0.5,
                               sleeper=sleeps.append)


@unittest.skipUnless(ConnectorClient.HELPER.is_file(),
                     "connector helper not present on this machine")
class TestConnectorRetry(unittest.TestCase):
    def test_recovers_after_two_503s(self):
        sleeps, calls = [], []
        seq = [_Proc(3, stderr="HTTP 503 from Meta Model API: service_overloaded"),
               _Proc(3, stderr="HTTP 503 from Meta Model API: service_overloaded"),
               _Proc(0, stdout='{"verdict": "approve"}')]

        def fake_run(cmd, input=None, capture_output=None, text=None, timeout=None):
            calls.append(1)
            return seq[len(calls) - 1]

        client = _connector_client(sleeps)
        with mock.patch("daas.llm.subprocess.run", fake_run):
            out = client.complete_json(prompts.REVIEWER, "{}")
        self.assertEqual(out, {"verdict": "approve"})
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [0.5, 1.0])  # exponential backoff
        self.assertEqual(client.retry_stats,
                         {"calls": 3, "retries": 2, "transient_failures": 2})

    def test_invalid_key_fails_immediately(self):
        sleeps, calls = [], []

        def fake_run(cmd, input=None, capture_output=None, text=None, timeout=None):
            calls.append(1)
            return _Proc(3, stderr="HTTP 401 from Meta Model API: invalid_api_key")

        client = _connector_client(sleeps)
        with mock.patch("daas.llm.subprocess.run", fake_run):
            with self.assertRaises(LLMError):
                client.complete_json(prompts.TRIAGE, "{}")
        self.assertEqual(len(calls), 1)
        self.assertEqual(sleeps, [])
        self.assertEqual(client.retry_stats["retries"], 0)

    def test_exhaustion_raises_after_max_attempts(self):
        sleeps, calls = [], []

        def fake_run(cmd, input=None, capture_output=None, text=None, timeout=None):
            calls.append(1)
            return _Proc(3, stderr="HTTP 503 from Meta Model API: service_overloaded")

        client = _connector_client(sleeps)
        with mock.patch("daas.llm.subprocess.run", fake_run):
            with self.assertRaises(LLMError) as ctx:
                client.complete_json(prompts.TRIAGE, "{}")
        self.assertIn("503", str(ctx.exception))
        self.assertEqual(len(calls), 3)
        self.assertEqual(client.retry_stats["retries"], 2)


class _FakeHttpResponse:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        body = {"choices": [{"message": {"content": '{"verdict": "approve"}'}}]}
        return json.dumps(body).encode()


def _http_error(code, body=b"service_overloaded"):
    return urllib.error.HTTPError(
        "https://api.meta.ai/v1/chat/completions", code, "err", None,
        io.BytesIO(body))


class TestDirectClientRetry(unittest.TestCase):
    def _client(self, sleeps):
        with mock.patch.dict(os.environ, {"MODEL_API_KEY": "dummy"}, clear=True):
            return MetaModelClient(max_attempts=3, backoff_base=0.5,
                                   sleeper=sleeps.append)

    def test_recovers_after_503(self):
        sleeps, calls = [], []

        def fake_urlopen(req, timeout=None):
            calls.append(1)
            if len(calls) < 3:
                raise _http_error(503)
            return _FakeHttpResponse()

        client = self._client(sleeps)
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            out = client.complete_json(prompts.REVIEWER, "{}")
        self.assertEqual(out, {"verdict": "approve"})
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [0.5, 1.0])
        self.assertEqual(client.retry_stats["retries"], 2)

    def test_400_fails_immediately(self):
        sleeps, calls = [], []

        def fake_urlopen(req, timeout=None):
            calls.append(1)
            raise _http_error(400, b"bad request")

        client = self._client(sleeps)
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(LLMError):
                client.complete_json(prompts.TRIAGE, "{}")
        self.assertEqual(len(calls), 1)
        self.assertEqual(client.retry_stats["retries"], 0)


class TestRetryDoc(unittest.TestCase):
    def test_tooling_doc_records_retry(self):
        text = (ROOT / "META_AI_TOOLING.md").read_text(encoding="utf-8")
        self.assertIn("Provider-transient retry", text)
        self.assertIn("503", text)
        self.assertIn("retry_stats", text)


if __name__ == "__main__":
    unittest.main()
