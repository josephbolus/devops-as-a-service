"""Pin the Meta AI tooling artifact (repo-root META_AI_TOOLING.md)
and the tooling mechanisms it describes.

The doc is a judged Tooling artifact: it must name the real model,
clients, and schemas, and stay honest about the undecided per-role
split. The mechanism tests go further than the doc: they prove, with
mocked transports and NO live API call, that BOTH live clients resolve
per-role models before the call and that the direct client sends
response_format json_object — the two transports had never both been
pinned before this file.
"""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))
from daas import prompts  # noqa: E402
from daas.llm import (  # noqa: E402
    AGENT_ROLES,
    ConnectorClient,
    MetaModelClient,
    MockClient,
    default_client,
)

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "META_AI_TOOLING.md"
DEFAULT = "muse-spark-1.3"

ROLE_KEYS = {
    "TRIAGE": ("kind", "summary", "acceptance"),
    "PLANNER": ("steps", "expected_files"),
    "CODER": ("edits", "file", "old", "new"),
    "REVIEWER": ("verdict", "notes"),
}


class TestToolingDoc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_names_model_endpoint_and_json_mode(self):
        for token in ("muse-spark-1.3", "https://api.meta.ai/v1",
                      "response_format", "json_object"):
            self.assertIn(token, self.text, token)

    def test_names_all_three_clients_honestly(self):
        for token in ("ConnectorClient", "MetaModelClient", "MockClient",
                      "NOT Meta AI tooling evidence",
                      "secure connection store"):
            self.assertIn(token, self.text, token)

    def test_names_all_roles_and_env_overrides(self):
        for role in AGENT_ROLES:
            self.assertIn(role, self.text, role)
            self.assertIn(f"DAAS_MODEL_{role}", self.text, role)

    def test_honest_not_claimed_section(self):
        self.assertIn("What is NOT claimed", self.text)
        self.assertIn("Per-role split: experiment run, decision recorded",
                      self.text)
        self.assertIn("Decision: keep the split", self.text)
        self.assertIn("muse-wonder-1.0", self.text)
        self.assertIn("split-runs.json", self.text)
        self.assertIn("PR #16", self.text)

    def test_root_readme_links_it(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("META_AI_TOOLING.md", readme)


class TestPromptSchemas(unittest.TestCase):
    def test_by_role_covers_exactly_the_agent_roles(self):
        self.assertEqual(set(prompts.BY_ROLE), set(AGENT_ROLES))

    def test_each_prompt_starts_with_its_role_and_demands_json_only(self):
        for role, prompt in prompts.BY_ROLE.items():
            self.assertTrue(prompt.startswith(role), role)
            self.assertIn("JSON only", prompt, role)
            self.assertIn("exactly these keys", prompt, role)

    def test_each_prompt_names_its_exact_keys(self):
        for role, keys in ROLE_KEYS.items():
            for key in keys:
                self.assertIn(f'"{key}"', prompts.BY_ROLE[role],
                              (role, key))

    def test_coder_rules_the_pipeline_depends_on(self):
        self.assertIn("VERBATIM", prompts.CODER)
        self.assertIn("unittest.TestCase", prompts.CODER)
        self.assertIn("does NOT collect bare pytest-style",
                      prompts.CODER)


class _FakeHttpResponse:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        body = {"choices": [{"message": {"content": '{"verdict": "approve"}'}}]}
        return json.dumps(body).encode()


class TestLiveTransportsResolveModels(unittest.TestCase):
    def test_direct_client_sends_json_object_and_resolved_model(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["payload"] = json.loads(req.data)
            return _FakeHttpResponse()

        with mock.patch.dict(os.environ, {"MODEL_API_KEY": "dummy",
                                          "DAAS_MODEL_REVIEWER": "strong-model"}):
            client = MetaModelClient()
            with mock.patch("urllib.request.urlopen", fake_urlopen):
                out = client.complete_json(prompts.REVIEWER, "{}")
        self.assertEqual(out, {"verdict": "approve"})
        self.assertEqual(captured["payload"]["model"], "strong-model")
        self.assertEqual(captured["payload"]["response_format"],
                         {"type": "json_object"})
        self.assertEqual(captured["payload"]["messages"][0]["role"],
                         "system")

    def test_direct_client_default_model_without_override(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["payload"] = json.loads(req.data)
            return _FakeHttpResponse()

        with mock.patch.dict(os.environ, {"MODEL_API_KEY": "dummy"},
                             clear=True):
            client = MetaModelClient()
            with mock.patch("urllib.request.urlopen", fake_urlopen):
                client.complete_json(prompts.TRIAGE, "{}")
        self.assertEqual(captured["payload"]["model"], DEFAULT)

    @unittest.skipUnless(ConnectorClient.HELPER.is_file(),
                         "connector helper not present on this machine")
    def test_connector_client_picks_up_env_overrides(self):
        with mock.patch.dict(os.environ,
                             {"DAAS_MODEL_CODER": "strong-model"},
                             clear=True):
            client = ConnectorClient()
        self.assertEqual(client.role_models, {"CODER": "strong-model"})

    @unittest.skipUnless(ConnectorClient.HELPER.is_file(),
                         "connector helper not present on this machine")
    def test_connector_client_passes_resolved_model_to_helper(self):
        captured = {}

        class _Proc:
            returncode = 0
            stdout = '{"edits": []}'
            stderr = ""

        def fake_run(cmd, input=None, capture_output=None, text=None,
                     timeout=None):
            captured["payload"] = json.loads(input)
            return _Proc()

        with mock.patch.dict(os.environ,
                             {"DAAS_MODEL_CODER": "strong-model"},
                             clear=True):
            client = ConnectorClient()
            with mock.patch("daas.llm.subprocess.run", fake_run):
                out = client.complete_json(prompts.CODER, "{}")
        self.assertEqual(out, {"edits": []})
        self.assertEqual(captured["payload"]["model"], "strong-model")
        self.assertEqual(captured["payload"]["system"], prompts.CODER)

    def test_default_client_selection(self):
        self.assertIsInstance(default_client(mock=True), MockClient)
        with mock.patch.dict(os.environ, {"MODEL_API_KEY": "dummy"},
                             clear=True):
            self.assertIsInstance(default_client(), MetaModelClient)


if __name__ == "__main__":
    unittest.main()
