"""Deterministic guardrail — runs BEFORE any LLM agent.

Destructive or irreversible requests escalate to a human and never reach
the coder, regardless of what a model would say. This is the demo's
trust beat (sprint plan, Oct 31–Nov 1), pulled forward as code on day 0
because it is cheaper to design the pipeline around it than to bolt it
on after the loop works.

Coverage hardened Oct 24 (maximizer iteration 1): the original five
patterns only caught the canonical phrasing ("delete/drop/truncate …
database/table"). Simple rewordings evaded it entirely — verified live:
"Erase the production database", "Permanently delete all customer
data", "Remove the legacy database", "Destroy the old database
backups", and "Clear out all production records" all passed through.
The verb and object sets are now broad, word order is checked both
ways, bulk-data phrasing is caught, and benign cleanups (removing an
unused import, deleting an obsolete comment, removing all unused
imports) still pass — see tests/test_guardrail.py for both sides
pinned as regression tests. Escalation is a human review, not a
refusal of service, so the patterns deliberately err toward catching
a destructive request phrased oddly over letting one slip to the coder.
"""
import re

_DESTRUCTIVE_VERBS = (
    r"(?:drop(?:s|ped|ping)?|delet(?:e|es|ed|ing)|truncat(?:e|es|ed|ing)|"
    r"eras(?:e|es|ed|ing)|destroy(?:s|ed|ing)?|wip(?:e|es|ed|ing)|"
    r"purg(?:e|es|ed|ing)|remov(?:e|es|ed|ing)|clear(?:s|ed|ing)?)"
)
_DATA_OBJECTS = (
    r"(?:database|db|tables?|schema|records?|customer data|user data|"
    r"all data|backups?)"
)

PATTERNS = [
    # verb … data object ("drop old tables", "erase the production database")
    (rf"\b{_DESTRUCTIVE_VERBS}\b.{{0,60}}\b{_DATA_OBJECTS}\b",
     "destructive operation on data"),
    # data object … verb, passive/reordered ("old tables need to be dropped")
    (rf"\b{_DATA_OBJECTS}\b.{{0,40}}\b{_DESTRUCTIVE_VERBS}\b",
     "destructive operation on data (reordered phrasing)"),
    # verb … named production/legacy/live asset ("remove the legacy system")
    (rf"\b{_DESTRUCTIVE_VERBS}\b.{{0,60}}\b(production|prod|legacy|live)\b",
     "destructive operation on a production/legacy asset"),
    # bulk data phrasing ("delete all customer data", "wipe every record")
    (rf"\b{_DESTRUCTIVE_VERBS}\b.{{0,40}}\b(?:all|every|entire)\s+"
     r"(?:data|records?|users?|customers?|tables?|databases?|files?|rows?|backups?|entries)\b",
     "bulk destructive operation"),
    (r"\brm\s+-rf\b", "recursive force delete"),
    (r"\bforce[- ]?push\b", "force push rewrites shared history"),
]


def check(title, body):
    """Return (blocked: bool, reason: str)."""
    text = f"{title}\n{body}".lower()
    for pattern, reason in PATTERNS:
        if re.search(pattern, text):
            return True, reason
    return False, ""
