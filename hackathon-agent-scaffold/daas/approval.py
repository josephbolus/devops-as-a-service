"""Human-approval handoff for guardrail escalations, plus resume.

When the deterministic guardrail blocks an issue, the pipeline does not
just refuse: it hands a human a structured approval request.

The request records, in machine-readable form and as a walkable
markdown artifact (the demo's trust beat):
- what was requested and why the guardrail escalated it,
- what the pipeline provably did NOT do (no model call, no files
  changed, no PR opened) - the safety claim is checkable, not asserted,
- the three decisions a human can actually make, and
- a blank decision record to fill in, so the outcome is auditable.

Approve-and-resume (backlog item 3, completed Oct 25): ``record_decision``
validates and records a human decision on a request. Only ``rescope``
can resume, and only with an explicit, narrower replacement issue
attached; that replacement re-enters ``pipeline.run`` and therefore
re-runs the deterministic guardrail before any model call - a rescoped
issue that is still destructive escalates again. ``reject`` and
``handle_manually`` close the request and never run agents.
"""
import copy
import json

DECISIONS = ("reject", "rescope", "handle_manually")
_STATUS_FOR = {"reject": "closed_rejected", "handle_manually": "closed_manual", "rescope": "approved_rescope"}

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
        "rescoped_issue": None,
        "decision_record": {
            "decision": None,
            "decided_by": None,
            "decided_at": None,
            "notes": None,
        },
    }


def record_decision(request, decision, decided_by, decided_at,
                    notes=None, rescoped_issue=None):
    """Return a new request with a validated human decision recorded.

    Pure: the input request is not mutated. Raises ValueError on an
    unknown decision, a missing decider/timestamp, or a rescope
    without a concrete replacement issue (title required).
    """
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}, got {decision!r}")
    if not str(decided_by or "").strip():
        raise ValueError("decided_by is required")
    if not str(decided_at or "").strip():
        raise ValueError("decided_at is required")
    if decision == "rescope":
        if not isinstance(rescoped_issue, dict) or not str(rescoped_issue.get("title") or "").strip():
            raise ValueError("rescope requires a rescoped_issue with a title")
    out = copy.deepcopy(request)
    out["status"] = _STATUS_FOR[decision]
    out["rescoped_issue"] = copy.deepcopy(rescoped_issue) if decision == "rescope" else None
    out["decision_record"] = {
        "decision": decision,
        "decided_by": decided_by,
        "decided_at": decided_at,
        "notes": notes,
    }
    return out


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
    record = request.get("decision_record") or {}
    if record.get("decision"):
        lines += [
            "",
            "### Decision record",
            "",
            f"- Decision: {record['decision']}",
            f"- Decided by: {record.get('decided_by') or ''}",
            f"- Decided at: {record.get('decided_at') or ''}",
            f"- Notes: {record.get('notes') or ''}",
        ]
        rescoped = request.get("rescoped_issue")
        if rescoped:
            lines += ["", f"Rescoped issue: {rescoped.get('title','')}"]
        lines.append("")
    else:
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
