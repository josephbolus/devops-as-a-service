"""Pin model fallback (iteration 28).

Motivation is the scorecard's own Tooling cap: until this iteration
only two Meta models had ever served a production role, and a
model-level failure had no recourse. These tests prove, with mocked
transports and NO live API call, that both live clients fall back to a
configured alternate model only on model-availability failures or
transient exhaustion — never on auth or other 4xx — and record
fallback_stats.
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
    fallback_models_from_env,
    is_model_error,
    resolve_fallback,
)

ROOT = Path(__file__).resolve().parents[2]
PRIMARY = "muse-wonder-1.0"
FALLBACK = "muse-spark-1.2"


class TestModelErrorClassification(unittest.TestCase):
    def test_model_markers_and_404(self):
        self.assertTrue(is_model_error("", code=404))
        self.assertTrue(is_model_error("model_not_found"))
        self.assertTrue(is_model_error("Unknown model: x"))
        self.assertFalse(is_model_error("", code=400))
        self.assertFalse(is_model_error("service_overloaded"))

    def test_auth_never_a_model_error(self):
        self.assertFalse(is_model_error("HTTP 401: invalid_api_key", code=404))

    def test_resolve_fallback(self):
        self.assertEqual(
            resolve_fallback(prompts.CODER, PRIMARY, FALLBACK, {}), FALLBACK)
        self.assertEqual(
            resolve_fallback(prompts.CODER, PRIMARY, None,
                             {"CODER": "muse-spark-1.1"}), "muse-spark-1.1")
        self.assertIsNone(resolve_fallback(prompts.CODER, PRIMARY, PRIMARY, {}))
        self.assertIsNone(resolve_fallback(prompts.CODER, PRIMARY, None, {}))

    def test_fallback_env_parsing(self):
        env = {"DAAS_FALLBACK_CODER": FALLBACK, "DAAS_MODEL_CODER": PRIMARY}
        self.assertEqual(fallback_models_from_env(env), {"CODER": FALLBACK})


class _Proc:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _connector_client(sleeps, **kw):
    with mock.patch.dict(os.environ, {}, clear=True):
        return ConnectorClient(model=PRIMARY, sleeper=sleeps.append,
                               fallback_model=FALLBACK, **kw)


@unittest.skipUnless(ConnectorClient.HELPER.is_file(),
                     "connector helper not present on this machine")
class TestConnectorFallback(unittest.TestCase):
    def _run_with_models(self, fail_models, fail_proc):
        sleeps, seen = [], []

        def fake_run(cmd, input=None, capture_output=None, text=None,
                     timeout=None):
            model = json.loads(input)["model"]
            seen.append(model)
            if model in fail_models:
                return fail_proc
            return _Proc(0, stdout='{"verdict": "approve"}')

        client = _connector_client(sleeps)
        with mock.patch("daas.llm.subprocess.run", fake_run):
            try:
                out = client.complete_json(prompts.REVIEWER, "{}")
            except LLMError as e:
                out = e
        return client, seen, out

    def test_model_not_found_falls_back(self):
        client, seen, out = self._run_with_models(
            {PRIMARY}, _Proc(3, stderr="HTTP 404 from Meta Model API: "
                                       "model_not_found"))
        self.assertEqual(out, {"verdict": "approve"})
        self.assertEqual(seen, [PRIMARY, FALLBACK])
        self.assertEqual(client.fallback_stats,
                         {"fallbacks": 1, "fallback_successes": 1})

    def test_transient_exhaustion_falls_back(self):
        client, seen, out = self._run_with_models(
            {PRIMARY}, _Proc(3, stderr="HTTP 503 from Meta Model API: "
                                       "service_overloaded"))
        self.assertEqual(out, {"verdict": "approve"})
        self.assertEqual(seen, [PRIMARY] * 3 + [FALLBACK])
        self.assertEqual(client.retry_stats["retries"], 2)
        self.assertEqual(client.fallback_stats["fallback_successes"], 1)

    def test_auth_failure_never_falls_back(self):
        client, seen, out = self._run_with_models(
            {PRIMARY, FALLBACK},
            _Proc(3, stderr="HTTP 401 from Meta Model API: invalid_api_key"))
        self.assertIsInstance(out, LLMError)
        self.assertEqual(seen, [PRIMARY])
        self.assertEqual(client.fallback_stats["fallbacks"], 0)

    def test_bad_request_never_falls_back(self):
        client, seen, out = self._run_with_models(
            {PRIMARY, FALLBACK},
            _Proc(3, stderr="HTTP 400 from Meta Model API: bad request"))
        self.assertIsInstance(out, LLMError)
        self.assertEqual(seen, [PRIMARY])


class _FakeHttpResponse:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        body = {"choices": [{"message": {
            "content": '{"verdict": "approve"}'}}]}
        return json.dumps(body).encode()


def _http_error(code, body):
    return urllib.error.HTTPError(
        "https://api.meta.ai/v1/chat/completions", code, "err", None,
        io.BytesIO(body))


class TestDirectClientFallback(unittest.TestCase):
    def test_model_not_found_falls_back(self):
        sleeps, seen = [], []

        def fake_urlopen(req, timeout=None):
            model = json.loads(req.data)["model"]
            seen.append(model)
            if model == PRIMARY:
                raise _http_error(404, b"model_not_found")
            return _FakeHttpResponse()

        with mock.patch.dict(os.environ, {"MODEL_API_KEY": "dummy"},
                             clear=True):
            client = MetaModelClient(model=PRIMARY, sleeper=sleeps.append,
                                     fallback_model=FALLBACK)
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            out = client.complete_json(prompts.REVIEWER, "{}")
        self.assertEqual(out, {"verdict": "approve"})
        self.assertEqual(seen, [PRIMARY, FALLBACK])
        self.assertEqual(client.fallback_stats["fallback_successes"], 1)


class TestFallbackDoc(unittest.TestCase):
    def test_tooling_doc_records_fallback(self):
        text = (ROOT / "META_AI_TOOLING.md").read_text(encoding="utf-8")
        self.assertIn("Model fallback", text)
        self.assertIn("muse-spark-1.2", text)
        self.assertIn("fallback_stats", text)


if __name__ == "__main__":
    unittest.main()
