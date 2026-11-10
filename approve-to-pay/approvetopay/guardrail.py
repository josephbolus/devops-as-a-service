"""Deterministic guardrail for Approve-to-Pay.

Pure functions, no I/O, no model calls. The verdict path is code all the
way down: the same job always gets the same verdict, and a judge can read
exactly why in `check()`.

Checks run in a fixed order and the first failure wins, so the reported
reason is stable:

1. category_not_allowed - category not on the policy allowlist
2. over_budget          - quoted price exceeds the job's budget cap
3. price_changed        - checkout price differs from the quoted price
                          (the amount captured must be the amount that was
                          quoted and approved; any drift, up or down,
                          blocks for re-approval)
4. over_budget          - checkout price exceeds the budget cap
                          (unreachable while check 3 stands, kept so the
                          rule "never capture above cap" holds even if the
                          drift rule is ever relaxed)

Money is handled as Decimal, parsed from strings, never floats.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

REASON_CATEGORY = "category_not_allowed"
REASON_OVER_BUDGET = "over_budget"
REASON_PRICE_CHANGED = "price_changed"


@dataclass(frozen=True)
class Verdict:
    passed: bool
    reason: str | None  # None when passed

    @property
    def outcome(self) -> str:
        return "pass" if self.passed else "block"


def money(value: str | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(value)


def check(job: dict, policy: dict) -> Verdict:
    """Return the guardrail verdict for one purchasing job."""
    allowlist = set(policy["category_allowlist"])
    if job["category"] not in allowlist:
        return Verdict(False, REASON_CATEGORY)

    cap = money(job["budget_cap"])
    quoted = money(job["quoted_price"])
    checkout = money(job["checkout_price"])

    if quoted > cap:
        return Verdict(False, REASON_OVER_BUDGET)
    if checkout != quoted:
        return Verdict(False, REASON_PRICE_CHANGED)
    if checkout > cap:
        return Verdict(False, REASON_OVER_BUDGET)

    return Verdict(True, None)
