"""PayPal Orders API v2 client (sandbox), with a fixture-backed mock mode.

Two modes, chosen by environment:

- **Live mode** — used when PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET are
  both set. Talks to the real PayPal sandbox (or live, if PAYPAL_ENV=live)
  with stdlib urllib: OAuth client-credentials token -> create order
  (intent CAPTURE) -> capture. Credentials are read from the environment
  only; they are never hardcoded, logged, or written anywhere.

- **Mock mode** — used when either credential is absent. Clearly labeled
  in every log line and report. Responses come from fixtures/mock_orders.json
  and mirror the real API shapes, so the guardrail, approval gate,
  decision log and report are fully testable before credentials land.

Naming keeps the two approvals distinct, because the whole product lives
in the gap between them:

- **Payer approval** is PayPal's step: the buyer approves the payment on
  PayPal's own page (the `payer-action` link returned at order creation).
- **Console approval** is Approve-to-Pay's human gate (pipeline.py): our
  approver authorizes the spend. The order sits UNCAPTURED after payer
  approval until the console approver says yes. A "no" means `capture()`
  is never called.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

FIXTURES_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "mock_orders.json"

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"
LIVE_BASE = "https://api-m.paypal.com"


@dataclass
class Order:
    order_id: str
    status: str  # CREATED after create; COMPLETED after capture
    payer_action_url: str | None  # PayPal's payer-approval link ("approve" rel on older responses)
    mode: str  # "live" | "mock"


@dataclass
class Capture:
    order_id: str
    capture_id: str | None
    status: str  # COMPLETED on success


class PayPalClient:
    """Live Orders API client. Construct via `from_env()`."""

    mode = "live"

    def __init__(self, client_id: str, client_secret: str, base_url: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self.base_url = base_url
        self._token: str | None = None
        # Test/diagnostic hook: every capture() invocation is recorded here
        # so the never-capture-on-no invariant is directly assertable.
        self.capture_calls: list[str] = []

    # -- HTTP plumbing -------------------------------------------------
    def _request(self, method: str, path: str, body: dict | None = None,
                 headers: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
        return json.loads(raw) if raw else {}

    def _access_token(self) -> str:
        if self._token:
            return self._token
        basic = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()).decode()
        req = urllib.request.Request(
            self.base_url + "/v1/oauth2/token",
            data=b"grant_type=client_credentials", method="POST")
        req.add_header("Authorization", f"Basic {basic}")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=30) as resp:
            self._token = json.loads(resp.read())["access_token"]
        return self._token

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token()}"}

    # -- Orders API ----------------------------------------------------
    def create_order(self, *, amount: str, currency: str, description: str,
                     reference_id: str) -> Order:
        body = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": reference_id,
                "description": description,
                "amount": {"currency_code": currency, "value": amount},
            }],
        }
        resp = self._request("POST", "/v2/checkout/orders", body, self._auth())
        payer_url = None
        for link in resp.get("links", []):
            if link.get("rel") in ("payer-action", "approve"):
                payer_url = link.get("href")
        return Order(order_id=resp["id"], status=resp.get("status", "CREATED"),
                     payer_action_url=payer_url, mode=self.mode)

    def capture(self, order_id: str) -> Capture:
        self.capture_calls.append(order_id)
        resp = self._request(
            "POST", f"/v2/checkout/orders/{order_id}/capture", {}, self._auth())
        capture_id = None
        try:
            capture_id = (resp["purchase_units"][0]["payments"]
                          ["captures"][0]["id"])
        except (KeyError, IndexError):
            pass
        return Capture(order_id=order_id, capture_id=capture_id,
                       status=resp.get("status", ""))


class MockPayPalClient:
    """Fixture-backed stand-in with the same interface as PayPalClient."""

    mode = "mock"

    def __init__(self, fixtures_path: Path = FIXTURES_PATH):
        self._fixtures = json.loads(Path(fixtures_path).read_text())
        self.capture_calls: list[str] = []
        self.created_orders: list[str] = []

    def create_order(self, *, amount: str, currency: str, description: str,
                     reference_id: str) -> Order:
        order_id = f"MOCK-{reference_id}"
        self.created_orders.append(order_id)
        template = self._fixtures["create_order_response"]
        url = None
        for link in template["links"]:
            if link.get("rel") == "payer-action":
                url = link["href"].format(order_id=order_id)
        return Order(order_id=order_id, status=template["status"],
                     payer_action_url=url, mode=self.mode)

    def capture(self, order_id: str) -> Capture:
        self.capture_calls.append(order_id)
        template = self._fixtures["capture_response"]
        capture = (template["purchase_units"][0]["payments"]["captures"][0])
        return Capture(order_id=order_id,
                       capture_id=f"MOCKCAP-{order_id}",
                       status=capture["status"])


def from_env() -> PayPalClient | MockPayPalClient:
    """Live client if both credentials are set, else the labeled mock."""
    client_id = os.environ.get("PAYPAL_CLIENT_ID")
    client_secret = os.environ.get("PAYPAL_CLIENT_SECRET")
    if client_id and client_secret:
        base = LIVE_BASE if os.environ.get("PAYPAL_ENV") == "live" else SANDBOX_BASE
        return PayPalClient(client_id, client_secret, base)
    return MockPayPalClient()
