"""Baseline tests for the expansion modules (issues #4/#8/#9).

These pin only the behavior that is correct TODAY: each seeded defect
lives in a case these tests deliberately do not cover, exactly like
the Tier-1 pagination bug (full pages) is not covered by
test_baseline.py. Every test here passes with the bugs present.
"""
import unittest

from app.alerts import describe_rule
from app.config import DEFAULTS, env_overrides, load_config
from app.health import overall_status


class ConfigBaseline(unittest.TestCase):
    def test_defaults_when_no_env(self):
        self.assertEqual(load_config({}), DEFAULTS)

    def test_env_overrides_translation(self):
        out = env_overrides({"APP_PORT": "9090", "APP_DEBUG": "true"})
        self.assertEqual(out, {"port": 9090, "debug": True})


class HealthBaseline(unittest.TestCase):
    def test_all_ok_is_healthy(self):
        checks = [{"name": "database", "ok": True, "critical": True},
                  {"name": "cache", "ok": True, "critical": False}]
        self.assertEqual(overall_status(checks), "healthy")

    def test_all_down_is_unhealthy(self):
        checks = [{"name": "database", "ok": False, "critical": True},
                  {"name": "cache", "ok": False, "critical": False}]
        self.assertEqual(overall_status(checks), "unhealthy")


class AlertsBaseline(unittest.TestCase):
    def test_describe_rule(self):
        self.assertEqual(describe_rule("latency_ms", 500),
                         "page when latency_ms > 500")

    def test_at_threshold_does_not_page(self):
        from app.alerts import should_page
        self.assertFalse(should_page("latency_ms", 500, 500))


if __name__ == "__main__":
    unittest.main()
