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
client's default model. The split is a Day-1 (Oct 27) decision; until
then every role runs the default.
"""
import json
import os
import urllib.request


class LLMError(RuntimeError):
    pass


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
                 role_models=None):
        self.key = os.environ.get("MODEL_API_KEY") or os.environ.get("META_API_KEY")
        if not self.key:
            raise LLMError("Set MODEL_API_KEY (or META_API_KEY) for the Meta Model API.")
        self.model = model
        self.base = base.rstrip("/")
        self.role_models = role_models_from_env() if role_models is None else role_models

    def complete_json(self, system, user):
        body = json.dumps({
            "model": resolve_model(system, self.model, self.role_models),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }).encode()
        req = urllib.request.Request(
            self.base + "/chat/completions",
            data=body,
            headers={
                "Authorization": "Bearer " + self.key,
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        text = data["choices"][0]["message"]["content"]
        return json.loads(text)


class MockClient:
    """Canned per-agent responses for the Tier-1 seed issue + guardrail.

    Keyed by the agent name passed as the system prompt's first word.
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

    def complete_json(self, system, user):
        agent = system.strip().split()[0].upper()
        if agent not in self.RESPONSES:
            raise LLMError(f"MockClient has no canned response for agent {agent!r}")
        return json.loads(json.dumps(self.RESPONSES[agent]))


def default_client(mock=False):
    return MockClient() if mock else MetaModelClient()
