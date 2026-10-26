"""Single LLM abstraction for the whole pipeline.

Every agent calls `LLMClient.complete_json(system, user)` and never talks
to a provider directly, so the model can be swapped without touching
agent logic (same pattern as the income-goal prototype's llm.py).

Providers:
- MetaModelClient: Meta Model API (public preview), OpenAI-compatible
  chat completions at https://api.meta.ai/v1, model `muse-spark-1.3`.
  Key from env MODEL_API_KEY (promptfoo docs) or META_API_KEY
  (LiteLLM docs) — both names are accepted here.
- MockClient: deterministic canned responses keyed by agent name, for
  offline plumbing tests. It proves the pipeline end to end; it is NOT
  the intelligence the judges will see.

Per-role models: each agent role (TRIAGE, PLANNER, CODER, REVIEWER —
the system prompt's first word, the same convention MockClient uses) can
be pointed at a different model via `DAAS_MODEL_<ROLE>` env vars, e.g.
DAAS_MODEL_CODER=<stronger model>. Roles without an override use the
client's default model. Split decided Oct 25, 2026 by measured
experiment (repo-root META_AI_TOOLING.md, eval-scorecard/split-runs.json):
the entry's live configuration sets CODER and REVIEWER to
muse-wonder-1.0; TRIAGE and PLANNER run the default.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


class LLMError(RuntimeError):
    pass


# --- Provider-transient retry (iteration 22) ---------------------------------
# Measured motivation: the Oct 25 Judge Mode live tour lost its Tier 2
# run when the REVIEWER call failed with a provider HTTP 503
# (`service_overloaded`) and the client raised immediately — one
# transient provider blip killed an otherwise-passing run (its tests
# stage had already passed 6 -> 11). Live clients now retry TRANSIENT
# failures only (HTTP 429/500/502/503/504, overload / rate-limit /
# timeout markers) with exponential backoff, up to `max_attempts`
# total attempts. Auth and other 4xx failures are never retried:
# retrying an invalid key or a malformed request cannot help and
# would only hide the real error. Each client records `retry_stats`
# ({calls, retries, transient_failures}) so a run can report whether
# a retry actually fired — no silent recovery.
TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504}
NON_TRANSIENT_MARKERS = ("invalid_api_key", "invalid api key",
                         "unauthorized", "forbidden", "invalid_api")
TRANSIENT_MARKERS = ("service_overloaded", "overloaded", "temporarily",
                     "rate limit", "rate_limit", "too many requests",
                     "timed out", "timeout", "try again")


def is_transient_error(text, code=None):
    """True only for provider-transient failures worth retrying."""
    low = (text or "").lower()
    if any(m in low for m in NON_TRANSIENT_MARKERS):
        return False
    if code is not None:
        return code in TRANSIENT_HTTP_CODES
    for m in re.findall(r"\bhttp\s+(\d{3})\b", low):
        if int(m) in TRANSIENT_HTTP_CODES:
            return True
    return any(m in low for m in TRANSIENT_MARKERS)


def _backoff(sleeper, base, attempt):
    sleeper(base * (2 ** attempt))


# --- Model fallback (iteration 28) -------------------------------------------
# Measured motivation: until this iteration only two Meta models had
# ever served a production role (muse-spark-1.3 and muse-wonder-1.0),
# and a model-level failure (an unavailable / unknown model, or a
# transient failure that survives every retry) killed the call with no
# recourse. Clients now accept a fallback model — per role via
# `DAAS_FALLBACK_<ROLE>`, or one global fallback via
# `DAAS_FALLBACK_MODEL` — and use it ONLY when the primary call fails
# for a model-availability reason (HTTP 404, model_not_found / unknown
# model markers) or after transient retries are exhausted. Auth and
# other 4xx failures NEVER fall back: a bad key fails on every model,
# and falling back would only hide it. Fallbacks are recorded in
# `fallback_stats` ({fallbacks, fallback_successes}), never silent.
MODEL_ERROR_MARKERS = ("model_not_found", "model not found",
                       "unknown model", "invalid model",
                       "no such model", "model is not available",
                       "model unavailable", "model_not_available")


def is_model_error(text, code=None):
    """True only for model-availability failures worth falling back on."""
    low = (text or "").lower()
    if any(m in low for m in NON_TRANSIENT_MARKERS):
        return False
    if code == 404:
        return True
    return any(m in low for m in MODEL_ERROR_MARKERS)


def _fallback_warranted(error_text):
    if any(m in (error_text or "").lower() for m in NON_TRANSIENT_MARKERS):
        return False
    return is_model_error(error_text) or is_transient_error(error_text)


def fallback_models_from_env(environ=None):
    """Per-role fallback models from DAAS_FALLBACK_<ROLE> env vars."""
    env = os.environ if environ is None else environ
    out = {}
    for role in AGENT_ROLES:
        model = env.get(f"DAAS_FALLBACK_{role}")
        if model:
            out[role] = model
    return out


def resolve_fallback(system, primary, fallback_model, fallback_models):
    """Fallback model for this call, or None if none / same as primary."""
    words = system.strip().split()
    role = "".join(ch for ch in words[0] if ch.isalnum()).upper() if words else ""
    candidate = (fallback_models or {}).get(role, fallback_model)
    return candidate if candidate and candidate != primary else None


AGENT_ROLES = ("TRIAGE", "PLANNER", "CODER", "REVIEWER")


def role_models_from_env(environ=None):
    """Per-role model overrides from DAAS_MODEL_<ROLE> env vars."""
    env = os.environ if environ is None else environ
    out = {}
    for role in AGENT_ROLES:
        model = env.get(f"DAAS_MODEL_{role}")
        if model:
            out[role] = model
    return out


def resolve_model(system, default, role_models):
    """Model for this call: the role's override, else the default.

    Role = the system prompt's first word (TRIAGE, PLANNER, ...), the
    same convention MockClient keys its canned responses by.
    """
    words = system.strip().split()
    role = "".join(ch for ch in words[0] if ch.isalnum()).upper() if words else ""
    return role_models.get(role, default)


class MetaModelClient:
    def __init__(self, model="muse-spark-1.3", base="https://api.meta.ai/v1",
                 role_models=None, max_attempts=3, backoff_base=1.0,
                 sleeper=None, fallback_model=None, fallback_models=None):
        self.key = os.environ.get("MODEL_API_KEY") or os.environ.get("META_API_KEY")
        if not self.key:
            raise LLMError("Set MODEL_API_KEY (or META_API_KEY) for the Meta Model API.")
        self.model = model
        self.base = base.rstrip("/")
        self.role_models = role_models_from_env() if role_models is None else role_models
        self.max_attempts = max(1, int(max_attempts))
        self.backoff_base = float(backoff_base)
        self.sleeper = sleeper if sleeper is not None else time.sleep
        self.retry_stats = {"calls": 0, "retries": 0, "transient_failures": 0}
        self.fallback_model = (os.environ.get("DAAS_FALLBACK_MODEL")
                               if fallback_model is None else fallback_model)
        self.fallback_models = (fallback_models_from_env()
                                if fallback_models is None else fallback_models)
        self.fallback_stats = {"fallbacks": 0, "fallback_successes": 0}

    def complete_json(self, system, user):
        primary = resolve_model(system, self.model, self.role_models)
        try:
            return self._complete_with_model(system, user, primary)
        except LLMError as e:
            fb = resolve_fallback(system, primary, self.fallback_model,
                                  self.fallback_models)
            if not fb or not _fallback_warranted(str(e)):
                raise
            self.fallback_stats["fallbacks"] += 1
            out = self._complete_with_model(system, user, fb)
            self.fallback_stats["fallback_successes"] += 1
            return out

    def _complete_with_model(self, system, user, model):
        body = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }).encode()
        last_error = None
        for attempt in range(self.max_attempts):
            self.retry_stats["calls"] += 1
            req = urllib.request.Request(
                self.base + "/chat/completions",
                data=body,
                headers={
                    "Authorization": "Bearer " + self.key,
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read())
                text = data["choices"][0]["message"]["content"]
                return json.loads(text)
            except urllib.error.HTTPError as e:
                try:
                    detail = e.read().decode("utf-8", "replace")[:300]
                except Exception:
                    detail = str(e)
                last_error = LLMError(
                    f"Meta Model API HTTP {e.code}: {detail}")
                transient = is_transient_error(detail, code=e.code)
            except urllib.error.URLError as e:
                last_error = LLMError(f"Meta Model API network error: {e}")
                transient = is_transient_error(str(e))
            if transient:
                self.retry_stats["transient_failures"] += 1
            if not transient or attempt == self.max_attempts - 1:
                raise last_error
            self.retry_stats["retries"] += 1
            _backoff(self.sleeper, self.backoff_base, attempt)
        raise last_error  # pragma: no cover - loop always returns/raises


class MockClient:
    """Canned per-agent responses for the seed issues (Tier 1/2/3).

    Keyed by the agent name passed as the system prompt's first word,
    and — for TRIAGE/PLANNER/CODER, whose payloads carry the issue —
    by the issue title, so each seeded issue gets its own canned fix.
    REVIEWER payloads carry no issue, so the reviewer response is
    shared (a plain approve). Unknown issues fall back to Tier 1.
    """

    RESPONSES = {
        "TRIAGE": {
            "kind": "bug",
            "summary": "paginate() drops the last item of every full page",
            "acceptance": ["Full pages return exactly page_size items",
                           "Existing tests still pass"],
        },
        "PLANNER": {
            "steps": ["Reproduce with 20 items, page 2, page size 10",
                      "Fix the slice end in app/pagination.py",
                      "Add a regression test for a full last page"],
            "expected_files": ["app/pagination.py", "tests/test_pagination_regression.py"],
        },
        "CODER": {
            "edits": [
                {"file": "app/pagination.py",
                 "old": "return items[start : end - 1]  # BUG: the -1 drops the last item of full pages",
                 "new": "return items[start:end]"},
                {"file": "tests/test_pagination_regression.py",
                 "old": None,  # create file
                 "new": ("import unittest\n\nfrom app.pagination import paginate\n\n\n"
                         "class FullPageRegression(unittest.TestCase):\n"
                         "    def test_full_last_page(self):\n"
                         "        self.assertEqual(paginate(list(range(20)), 2, 10), list(range(10, 20)))\n\n\n"
                         "if __name__ == '__main__':\n    unittest.main()\n")},
            ]
        },
        "REVIEWER": {"verdict": "approve", "notes": "Diff limited to expected files; regression test added."},
    }

    # Per-issue overrides, keyed by exact seed-issue title.
    BY_ISSUE = {
        "Add retry with backoff to the HTTP client wrapper": {
            "TRIAGE": {
                "kind": "feature",
                "summary": "get() fails immediately on transient 5xx / network errors",
                "acceptance": ["5xx and network errors retried up to 3 times with 100ms-base exponential backoff",
                               "4xx raises HttpError after exactly 1 attempt",
                               "Existing tests still pass"],
            },
            "PLANNER": {
                "steps": ["Add a retry loop to get() in app/http_client.py (5xx/network only, never 4xx)",
                          "Exponential backoff: 100ms, 200ms, 400ms between attempts",
                          "Add tests for 5xx-then-success, persistent 5xx, and 4xx-no-retry"],
                "expected_files": ["app/http_client.py", "tests/test_http_retry.py"],
            },
            "CODER": {
                "edits": [
                    {"file": "app/http_client.py",
                     "old": "import urllib.request\nimport urllib.error",
                     "new": "import time\nimport urllib.request\nimport urllib.error"},
                    {"file": "app/http_client.py",
                     "old": ("def get(url, opener=None):\n"
                             "    \"\"\"GET `url` and return the response body as text. Single attempt.\"\"\"\n"
                             "    opener = opener or urllib.request.urlopen\n"
                             "    try:\n"
                             "        with opener(url) as resp:\n"
                             "            return resp.read().decode(\"utf-8\")\n"
                             "    except urllib.error.HTTPError as e:\n"
                             "        raise HttpError(e.code, str(e)) from e"),
                     "new": ("def get(url, opener=None, max_retries=3, backoff_base=0.1, sleep=time.sleep):\n"
                             "    \"\"\"GET `url` and return the body as text.\n\n"
                             "    Retries 5xx responses and network errors up to `max_retries`\n"
                             "    times with exponential backoff (backoff_base * 2**attempt\n"
                             "    seconds). 4xx responses are never retried.\n"
                             "    \"\"\"\n"
                             "    opener = opener or urllib.request.urlopen\n"
                             "    for attempt in range(max_retries + 1):\n"
                             "        try:\n"
                             "            with opener(url) as resp:\n"
                             "                return resp.read().decode(\"utf-8\")\n"
                             "        except urllib.error.HTTPError as e:\n"
                             "            if e.code < 500 or attempt == max_retries:\n"
                             "                raise HttpError(e.code, str(e)) from e\n"
                             "        except urllib.error.URLError:\n"
                             "            if attempt == max_retries:\n"
                             "                raise\n"
                             "        sleep(backoff_base * (2 ** attempt))")},
                    {"file": "tests/test_http_retry.py",
                     "old": None,
                     "new": ("import unittest\nimport urllib.error\n\n"
                             "from app.http_client import HttpError, get\n\n\n"
                             "def _err(code):\n"
                             "    return urllib.error.HTTPError('http://x', code, 'err', None, None)\n\n\n"
                             "class _Resp:\n"
                             "    def __enter__(self): return self\n"
                             "    def __exit__(self, *a): return False\n"
                             "    def read(self): return b'ok'\n\n\n"
                             "class Retry(unittest.TestCase):\n"
                             "    def test_5xx_then_success(self):\n"
                             "        calls = []\n"
                             "        def opener(url):\n"
                             "            calls.append(1)\n"
                             "            if len(calls) < 3: raise _err(503)\n"
                             "            return _Resp()\n"
                             "        self.assertEqual(get('http://x', opener=opener, sleep=lambda s: None), 'ok')\n"
                             "        self.assertEqual(len(calls), 3)\n\n"
                             "    def test_4xx_never_retried(self):\n"
                             "        calls = []\n"
                             "        def opener(url):\n"
                             "            calls.append(1); raise _err(400)\n"
                             "        with self.assertRaises(HttpError):\n"
                             "            get('http://x', opener=opener, sleep=lambda s: None)\n"
                             "        self.assertEqual(len(calls), 1)\n\n"
                             "    def test_persistent_5xx_exhausts_retries(self):\n"
                             "        calls = []\n"
                             "        def opener(url):\n"
                             "            calls.append(1); raise _err(503)\n"
                             "        with self.assertRaises(HttpError):\n"
                             "            get('http://x', opener=opener, sleep=lambda s: None)\n"
                             "        self.assertEqual(len(calls), 4)\n\n\n"
                             "if __name__ == '__main__':\n    unittest.main()\n")},
                ]
            },
        },
        "Make the CLI output machine-readable": {
            "TRIAGE": {
                "kind": "feature",
                "summary": "CLI prints only the human report; scripts cannot consume it",
                "acceptance": ["--json emits the REPORT data as one JSON document on stdout",
                               "Human output stays the default and is unchanged",
                               "Existing tests still pass"],
            },
            "PLANNER": {
                "steps": ["Add json_report() to app/report.py returning the REPORT dict as JSON",
                          "Branch on --json in app/cli.py main(); human output stays default",
                          "Add tests that --json parses and matches REPORT, and default output is unchanged"],
                "expected_files": ["app/cli.py", "app/report.py", "tests/test_cli_json.py"],
            },
            "CODER": {
                "edits": [
                    {"file": "app/report.py",
                     "old": "    return \"\\n\".join(lines)",
                     "new": ("    return \"\\n\".join(lines)\n\n\n"
                             "def json_report(report=REPORT):\n"
                             "    import json\n\n"
                             "    return json.dumps(report)")},
                    {"file": "app/cli.py",
                     "old": "from app.report import human_report",
                     "new": "from app.report import human_report, json_report"},
                    {"file": "app/cli.py",
                     "old": ("    # Tier-3 seed issue: --json is not implemented yet.\n"
                             "    print(human_report())"),
                     "new": ("    if \"--json\" in argv:\n"
                             "        print(json_report())\n"
                             "    else:\n"
                             "        print(human_report())")},
                    {"file": "tests/test_cli_json.py",
                     "old": None,
                     "new": ("import io\nimport json\nimport unittest\n"
                             "from contextlib import redirect_stdout\n\n"
                             "from app.cli import main\nfrom app.report import REPORT\n\n\n"
                             "class CliJson(unittest.TestCase):\n"
                             "    def test_json_flag_emits_report_as_json(self):\n"
                             "        buf = io.StringIO()\n"
                             "        with redirect_stdout(buf):\n"
                             "            self.assertEqual(main(['--json']), 0)\n"
                             "        self.assertEqual(json.loads(buf.getvalue()), REPORT)\n\n"
                             "    def test_default_output_stays_human(self):\n"
                             "        buf = io.StringIO()\n"
                             "        with redirect_stdout(buf):\n"
                             "            self.assertEqual(main([]), 0)\n"
                             "        self.assertIn('demo-api', buf.getvalue())\n"
                             "        self.assertFalse(buf.getvalue().lstrip().startswith('{'))\n\n\n"
                             "if __name__ == '__main__':\n    unittest.main()\n")},
                ]
            },
        },
    }

    def complete_json(self, system, user):
        agent = system.strip().split()[0].upper()
        if agent not in self.RESPONSES:
            raise LLMError(f"MockClient has no canned response for agent {agent!r}")
        response = self.RESPONSES[agent]
        try:
            payload = json.loads(user)
        except (TypeError, ValueError):
            payload = {}
        issue = payload.get("issue") or payload
        title = issue.get("title") if isinstance(issue, dict) else None
        override = self.BY_ISSUE.get(title, {}).get(agent)
        if override is not None:
            response = override
        return json.loads(json.dumps(response))


class ConnectorClient:
    """Meta Model API through the custom.meta-model-api connector.

    Used when no env key is set: the API key stays in Muse's secure
    connection store and never enters this process — each call shells
    out to the connector helper, which carries a surrogate credential
    the runtime swaps for the real key on the outbound request.
    """

    HELPER = (Path.home() / "workspace" / "custom-connectors"
              / "custom.meta-model-api" / "bin" / "meta_api.py")

    def __init__(self, model="muse-spark-1.3", role_models=None,
                 max_attempts=3, backoff_base=1.0, sleeper=None,
                 fallback_model=None, fallback_models=None):
        if not self.HELPER.is_file():
            raise LLMError(f"Connector helper not found at {self.HELPER}")
        self.model = model
        self.role_models = role_models_from_env() if role_models is None else role_models
        self.max_attempts = max(1, int(max_attempts))
        self.backoff_base = float(backoff_base)
        self.sleeper = sleeper if sleeper is not None else time.sleep
        self.retry_stats = {"calls": 0, "retries": 0, "transient_failures": 0}
        self.fallback_model = (os.environ.get("DAAS_FALLBACK_MODEL")
                               if fallback_model is None else fallback_model)
        self.fallback_models = (fallback_models_from_env()
                                if fallback_models is None else fallback_models)
        self.fallback_stats = {"fallbacks": 0, "fallback_successes": 0}

    def complete_json(self, system, user):
        primary = resolve_model(system, self.model, self.role_models)
        try:
            return self._complete_with_model(system, user, primary)
        except LLMError as e:
            fb = resolve_fallback(system, primary, self.fallback_model,
                                  self.fallback_models)
            if not fb or not _fallback_warranted(str(e)):
                raise
            self.fallback_stats["fallbacks"] += 1
            out = self._complete_with_model(system, user, fb)
            self.fallback_stats["fallback_successes"] += 1
            return out

    def _complete_with_model(self, system, user, model):
        payload = json.dumps({
            "model": model,
            "system": system,
            "user": user,
        })
        last_error = None
        for attempt in range(self.max_attempts):
            self.retry_stats["calls"] += 1
            proc = subprocess.run(
                [sys.executable, str(self.HELPER), "complete"],
                input=payload, capture_output=True, text=True, timeout=240)
            if proc.returncode == 0:
                return json.loads(proc.stdout)
            detail = proc.stderr.strip()[:300]
            last_error = LLMError(f"Connector call failed: {detail}")
            transient = is_transient_error(detail)
            if transient:
                self.retry_stats["transient_failures"] += 1
            if not transient or attempt == self.max_attempts - 1:
                raise last_error
            self.retry_stats["retries"] += 1
            _backoff(self.sleeper, self.backoff_base, attempt)
        raise last_error  # pragma: no cover - loop always returns/raises


def default_client(mock=False):
    if mock:
        return MockClient()
    if os.environ.get("MODEL_API_KEY") or os.environ.get("META_API_KEY"):
        return MetaModelClient()
    return ConnectorClient()
