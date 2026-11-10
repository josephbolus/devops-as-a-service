"""Append-only decision log (JSONL) — the audit trail for Approve-to-Pay.

Every job run appends exactly one line. The file is only ever opened in
append mode; entries are never edited or deleted in place. This is what
makes the claim "the approver said no, so $0 moved" auditable after the
fact (Meta-lessons addendum, fix 6): for every blocked purchase there is a
timestamped line with the order ID, the guardrail verdict, the approver
decision, and `capture_called: false`.

Entry fields:
    ts                ISO-8601 UTC timestamp of the run
    run_id            one id per runner invocation
    job_id            task-set job id (e.g. ATP-001)
    mode              "live" | "mock" (PayPal client mode)
    order_id          PayPal order id, or null if the guardrail blocked
                      the job before order creation
    guardrail_verdict "pass" | "block"
    guardrail_reason  null on pass; otherwise the guardrail reason
    payer_approval    "approved" | "not_reached"
    approver_decision "approve" | "deny" | "not_reached"
    capture_called    true only if PayPalClient.capture() was invoked
    capture_status    "COMPLETED" on success, otherwise null
    amount            the checkout amount that would have been captured
    expected_outcome  the frozen task set's expectation for this job
    actual_outcome    "capture" | "block_guardrail" | "block_approver"
    outcome_match     actual == expected
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DecisionLog:
    def __init__(self, path: Path):
        self.path = Path(path)

    def append(self, entry: dict) -> dict:
        entry = {"ts": utc_now_iso(), **entry}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:  # append-only
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in
                self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
