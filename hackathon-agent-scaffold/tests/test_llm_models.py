"""Per-role model resolution in the llm layer (no network, no key use)."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))
from daas.llm import MetaModelClient, resolve_model, role_models_from_env  # noqa: E402

DEFAULT = "muse-spark-1.3"


class ResolveModel(unittest.TestCase):
    def test_no_overrides_uses_default_for_every_role(self):
        for system in ("TRIAGE agent: classify", "PLANNER: plan",
                       "CODER agent: fix", "REVIEWER: review"):
            self.assertEqual(resolve_model(system, DEFAULT, {}), DEFAULT)

    def test_override_applies_to_its_role_only(self):
        roles = {"CODER": "strong-model", "REVIEWER": "strong-model"}
        self.assertEqual(resolve_model("CODER agent: fix", DEFAULT, roles), "strong-model")
        self.assertEqual(resolve_model("TRIAGE agent: classify", DEFAULT, roles), DEFAULT)

    def test_role_match_is_case_insensitive(self):
        self.assertEqual(resolve_model("coder: fix", DEFAULT, {"CODER": "m"}), "m")

    def test_empty_system_prompt_uses_default(self):
        self.assertEqual(resolve_model("   ", DEFAULT, {"CODER": "m"}), DEFAULT)


class RoleModelsFromEnv(unittest.TestCase):
    def test_reads_only_set_roles(self):
        env = {"DAAS_MODEL_CODER": "strong-model", "DAAS_MODEL_TRIAGE": ""}
        self.assertEqual(role_models_from_env(env), {"CODER": "strong-model"})

    def test_client_picks_up_env_overrides(self):
        with mock.patch.dict(os.environ, {"MODEL_API_KEY": "dummy",
                                          "DAAS_MODEL_CODER": "strong-model"}):
            client = MetaModelClient()
        self.assertEqual(client.role_models, {"CODER": "strong-model"})


if __name__ == "__main__":
    unittest.main()
