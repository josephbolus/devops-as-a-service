"""Deterministic guardrail — runs BEFORE any LLM agent.

Destructive or irreversible requests escalate to a human and never reach
the coder, regardless of what a model would say. This is the demo's
trust beat (sprint plan, Oct 31–Nov 1), pulled forward as code on day 0
because it is cheaper to design the pipeline around it than to bolt it
on after the loop works.
"""
import re

PATTERNS = [
    (r"\b(drop|delete|truncate)\b.*\b(database|table|tables|schema)\b", "destructive database operation"),
    (r"\bdelete\b.*\b(legacy|production|prod)\b", "deletion of a named production/legacy asset"),
    (r"\brm\s+-rf\b", "recursive force delete"),
    (r"\bforce[- ]?push\b", "force push rewrites shared history"),
    (r"\b(drop|wipe|purge)\b.*\b(all|every|entire)\b", "bulk destructive operation"),
]


def check(title, body):
    """Return (blocked: bool, reason: str)."""
    text = f"{title}\n{body}".lower()
    for pattern, reason in PATTERNS:
        if re.search(pattern, text):
            return True, reason
    return False, ""
