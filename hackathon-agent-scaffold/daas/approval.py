"""Human-approval handoff for guardrail escalations.

When the deterministic guardrail blocks an issue, the pipeline does not
just refuse: it hands a human a structured approval request. This is a
loop-sized slice of the Days 5-6 human-approval gate (sprint plan,
Oct 31-Nov 1) pulled forward on Oct 25 (maximizer iteration 5): the
request format exists and is test-pinned now, while the approve-and-
resume flow remains sprint work.

The request records, in machine-readable form and as a walkable
markdown artifact (the demo's trust beat):
- what was requested and why the guardrail escalated it,
- what the pipeline provably did NOT do (no model call, no files
  changed, no PR opened) - the safety claim is checkable, not asserted,
- the three decisions a human can actually make, and
- a blank decision record to fill in, so the outcome is auditable.
"""
import json

OPTIONS = [
    {
        "id": "reject",
        "label": "Reject - do not do this work",
        "effect": "Issue is closed as escalated; nothing runs.",
    },
    {
        "id": "rescope",
        "label": "Re-scope - file a safe, narrower issue instead",
        "effect": "A new, non-destructive issue can enter the pipeline normally.",
    },
    {
        "id": "handle_manually",
        "label": "Handle manually - a human does this outside the pipeline",
        "effect": "The destructive work, if still wanted, is performed by a "
                  "human under their own process; the agents never run it.",
    },
]


def build_request(issue, reason):
    """Structured approval request for a blocked issue. Pure function."""
    return {
        "type": "human_approval_request",
        "status": "escalated",
        "issue_title": issue["title"],
        "issue_body": issue.get("body", ""),
        "guardrail_reason": reason,
        "pipeline_actions": {
            "model_calls_made": 0,
            "agents_ran": [],
            "files_changed": [],
            "pr_opened": False,
        },
        "human_options": OPTIONS,
        "decision_record": {
            "decision": None,
            "decided_by": None,
            "decided_at": None,
            "notes": None,
        },
    }


def render_markdown(request):
    """Walkable markdown form of the approval request."""
    actions = request["pipeline_actions"]
    lines = [
        "ESCALATED - no PR opened.",
        "",
        "## Human approval request",
        "",
        f"Issue: {request['issue_title']}",
        f"Reason: {request['guardrail_reason']}.",
        "This request needs an explicit human decision.",
        "",
        "### What the pipeline did NOT do",
        "",
        f"- Model calls made: {actions['model_calls_made']}",
        f"- Agents ran: {', '.join(actions['agents_ran']) or 'none'}",
        f"- Files changed: {', '.join(actions['files_changed']) or 'none'}",
        f"- Pull request opened: {'yes' if actions['pr_opened'] else 'no'}",
        "",
        "### Options for the human reviewer",
        "",
    ]
    for i, opt in enumerate(request["human_options"], 1):
        lines.append(f"{i}. **{opt['label']}** - {opt['effect']}")
    lines += [
        "",
        "### Decision record (fill in)",
        "",
        "- Decision:",
        "- Decided by:",
        "- Decided at:",
        "- Notes:",
        "",
    ]
    return "\n".join(lines)


def to_json(request):
    return json.dumps(request, indent=2) + "\n"
