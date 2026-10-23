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
"""
import json
import os
import urllib.request


class LLMError(RuntimeError):
    pass


class MetaModelClient:
    def __init__(self, model="muse-spark-1.3", base="https://api.meta.ai/v1"):
        self.key = os.environ.get("MODEL_API_KEY") or os.environ.get("META_API_KEY")
        if not self.key:
            raise LLMError("Set MODEL_API_KEY (or META_API_KEY) for the Meta Model API.")
        self.model = model
        self.base = base.rstrip("/")

    def complete_json(self, system, user):
        body = json.dumps({
            "model": self.model,
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
