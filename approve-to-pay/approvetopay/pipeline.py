"""The Approve-to-Pay pipeline for a single purchasing job.

Stages, in order — the stage boundaries are the product:

1. **Guardrail** (guardrail.py, deterministic code). A blocked job stops
   here: no order is created and no money can move.
2. **Create order** (PayPal Orders API, intent CAPTURE). The order exists
   but is UNCAPTURED.
3. **Payer approval** — PayPal's own step: the payer approves on PayPal's
   page via the payer-action URL. This is *not* our approval gate. In
   batch/mock runs the fixture records the payer as approved; in an
   interactive live run the operator confirms after the payer approves.
4. **Console approval** — Approve-to-Pay's human gate. The approver sees
   the exact item and the exact checkout amount. "deny" ends the run:
   `capture()` is NEVER called and the order stays uncaptured ($0 moved).
   Batch runs take the decision from the job's scripted
   `approver_decision`; an interactive caller (the approval console)
   passes `decide`, a callable invoked at this stage with
   ``(job, order)`` that returns "approve" or "deny" — the pipeline
   pauses inside the callable while the human decides, with the order
   already created and still UNCAPTURED. Semantics are identical either
   way: anything other than "approve" means capture is never called.
5. **Capture** — only reached on guardrail pass + payer approval +
   console approval. Returns COMPLETED; the captured order is the receipt.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Callable

from . import guardrail
from .decision_log import DecisionLog
from .paypal_client import MockPayPalClient, Order, PayPalClient

OUTCOME_CAPTURE = "capture"
OUTCOME_BLOCK_GUARDRAIL = "block_guardrail"
OUTCOME_BLOCK_APPROVER = "block_approver"


def run_job(job: dict, policy: dict, client: PayPalClient | MockPayPalClient,
            log: DecisionLog, run_id: str,
            payer_approved: bool = True,
            decide: Callable[[dict, Order], str] | None = None) -> dict:
    """Run one job end to end, append its decision-log entry, return it."""
    amount = str(Decimal(job["checkout_price"]).quantize(Decimal("0.01")))
    entry: dict = {
        "run_id": run_id,
        "job_id": job["id"],
        "mode": client.mode,
        "order_id": None,
        "guardrail_verdict": None,
        "guardrail_reason": None,
        "payer_approval": "not_reached",
        "approver_decision": "not_reached",
        "capture_called": False,
        "capture_status": None,
        "amount": amount,
        "expected_outcome": job["expected_outcome"],
        "actual_outcome": None,
        "outcome_match": None,
    }

    # 1. Guardrail — before any order exists.
    verdict = guardrail.check(job, policy)
    entry["guardrail_verdict"] = verdict.outcome
    entry["guardrail_reason"] = verdict.reason
    if not verdict.passed:
        entry["actual_outcome"] = OUTCOME_BLOCK_GUARDRAIL
        entry["outcome_match"] = entry["actual_outcome"] == job["expected_outcome"]
        return log.append(entry)

    # 2. Create the order (UNCAPTURED).
    order = client.create_order(
        amount=amount,
        currency=policy["currency"],
        description=f"{job['item']} — {job['title']}",
        reference_id=job["id"],
    )
    entry["order_id"] = order.order_id

    # 3. Payer approval (PayPal's step, distinct from our gate).
    if not payer_approved:
        entry["actual_outcome"] = OUTCOME_BLOCK_APPROVER
        entry["outcome_match"] = entry["actual_outcome"] == job["expected_outcome"]
        return log.append(entry)
    entry["payer_approval"] = "approved"

    # 4. Console approval gate — the human decides. A "no" is final:
    #    capture is never called and the order stays uncaptured.
    #    Interactive callers decide live via the `decide` hook; batch
    #    runs use the job's scripted decision.
    decision = decide(job, order) if decide is not None else job["approver_decision"]
    entry["approver_decision"] = decision
    if decision != "approve":
        entry["actual_outcome"] = OUTCOME_BLOCK_APPROVER
        entry["outcome_match"] = entry["actual_outcome"] == job["expected_outcome"]
        return log.append(entry)

    # 5. Capture — the only path that moves money.
    capture = client.capture(order.order_id)
    entry["capture_called"] = True
    entry["capture_status"] = capture.status
    entry["actual_outcome"] = OUTCOME_CAPTURE
    entry["outcome_match"] = entry["actual_outcome"] == job["expected_outcome"]
    return log.append(entry)
