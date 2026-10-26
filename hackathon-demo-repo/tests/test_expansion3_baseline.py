"""Baseline tests for expansion batch 3 modules (#5/#10/#11).

Pin only correct-today behavior; each defect case is uncovered,
like the Tier-1 and batch-1/2 seeds. All pass with the bugs present.
"""
import unittest

from app.apiclient import fetch_all
from app.deploy import DeployAuthError, run_deploy
from app.retryer import backoff_delay, call_with_retry


class RetryerBaseline(unittest.TestCase):
    def test_backoff_delay_doubles(self):
        self.assertEqual(backoff_delay(0), 0.1)
        self.assertEqual(backoff_delay(2), 0.4)

    def test_first_try_success_never_sleeps(self):
        delays = []
        out = call_with_retry(lambda: "ok", sleep=delays.append)
        self.assertEqual(out, "ok")
        self.assertEqual(delays, [])


class DeployBaseline(unittest.TestCase):
    def test_valid_token_deploys(self):
        logs = []
        out = run_deploy("tok-valid", lambda t: True, logs.append)
        self.assertEqual(out, "deployed")
        self.assertIn("deploy succeeded", logs)

    def test_auth_error_type_exists(self):
        self.assertTrue(issubclass(DeployAuthError, Exception))


class ApiClientBaseline(unittest.TestCase):
    def test_single_page_result(self):
        def fetch_page(page):
            return {"items": [1, 2, 3], "next_page": None}
        self.assertEqual(fetch_all(fetch_page), [1, 2, 3])

    def test_empty_single_page(self):
        def fetch_page(page):
            return {"items": [], "next_page": None}
        self.assertEqual(fetch_all(fetch_page), [])


if __name__ == "__main__":
    unittest.main()
