"""V3 demo console (demo_ui.PAGE_V3 at /v3) + GET /api/meta.

The v3 page is the approved redesign (light + dark themes): additive
only. It consumes the same JSON API as the classic page, so these
tests pin (a) the classic PAGE is untouched and keeps its six pinned
substrings, (b) /v3 is served and wires the existing endpoints plus
the theme toggle, and (c) /api/meta reports the measured KPI values
from the eval-scorecard artifacts. Mock mode only, ephemeral port.
"""
import json
import sys
import threading
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import demo_ui  # noqa: E402


def _http(port, path, payload=None):
    url = f"http://127.0.0.1:{port}{path}"
    if payload is None:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.status, resp.headers.get_content_type(), resp.read().decode()
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.headers.get_content_type(), resp.read().decode()


class MetaKpis(unittest.TestCase):
    def test_meta_values_match_measured_records(self):
        meta = demo_ui.meta_kpis()
        self.assertEqual(meta["scenarios"],
                         {"passed": 12, "total": 12, "display": "12/12"})
        self.assertEqual(meta["net_new_tests"], 42)
        self.assertAlmostEqual(meta["est_cost_per_issue_usd"], 0.0326, places=4)
        self.assertEqual(meta["est_cost_per_issue_display"], "3.3¢")
        self.assertEqual(meta["live_prs_count"], 3)
        self.assertEqual(meta["live_prs"], demo_ui.LIVE_PR_URLS)
        self.assertEqual(meta["weighted_score"], 92.65)


class V3Page(unittest.TestCase):
    def test_v3_wires_existing_api_and_meta(self):
        for token in ("/api/issues", "/api/judge/run", "/api/run/",
                      "/api/guardrail", "/api/approval/decide", "/api/meta",
                      "results_card", "judgeBtn", "breakBtn"):
            self.assertIn(token, demo_ui.PAGE_V3, token)

    def test_v3_theme_toggle_defaults_light_and_persists(self):
        self.assertIn('data-theme="light"', demo_ui.PAGE_V3)
        self.assertIn("daas-v3-theme", demo_ui.PAGE_V3)
        self.assertIn('html[data-theme="dark"]', demo_ui.PAGE_V3)
        self.assertIn('id="themeLight"', demo_ui.PAGE_V3)
        self.assertIn('id="themeDark"', demo_ui.PAGE_V3)

    def test_v3_uses_approved_tokens(self):
        for token in ("--acc:#4350C8", "--ink:#151B28", "--navy:#1D2A47",
                      "--acc:#8B94F0", "--app:#0E1116", "--card:#151922"):
            self.assertIn(token, demo_ui.PAGE_V3, token)

    def test_classic_page_pins_untouched(self):
        for token in ("judgeBtn", "/api/judge/run", "judgeResults",
                      "judgeCaption", "card.cost", "Est. API cost"):
            self.assertIn(token, demo_ui.PAGE, token)


class V3Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = demo_ui.create_server("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_v3_served_as_html(self):
        status, ctype, body = _http(self.port, "/v3")
        self.assertEqual(status, 200)
        self.assertEqual(ctype, "text/html")
        self.assertIn("demo console v3", body)

    def test_root_still_serves_classic_page(self):
        status, ctype, body = _http(self.port, "/")
        self.assertEqual(status, 200)
        self.assertEqual(body, demo_ui.PAGE)

    def test_meta_endpoint_over_http(self):
        status, ctype, body = _http(self.port, "/api/meta")
        self.assertEqual(status, 200)
        self.assertEqual(ctype, "application/json")
        meta = json.loads(body)
        self.assertEqual(meta["scenarios"]["display"], "12/12")
        self.assertEqual(meta["weighted_score"], 92.65)


if __name__ == "__main__":
    unittest.main()
