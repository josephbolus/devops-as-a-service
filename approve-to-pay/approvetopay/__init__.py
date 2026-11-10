"""Approve-to-Pay: agentic purchasing with a deterministic guardrail and a
human approval gate in front of a real PayPal Orders API capture.

Pipeline per job (see pipeline.py):
    guardrail (pure code) -> create order -> payer approval (PayPal's step)
    -> console approver decision (our human gate) -> capture, or never.

The guardrail verdict path contains no LLM judgment: budget cap, category
allowlist and price-drift are checked in deterministic code, and a blocked
job never reaches order creation, let alone capture.
"""

__all__ = ["guardrail", "paypal_client", "decision_log", "pipeline"]
