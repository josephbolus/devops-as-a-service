#!/usr/bin/env python3
"""Approve-and-resume: act on a human decision for an escalated issue.

Usage:
  python3 run_resume.py --repo ../hackathon-demo-repo \
      --request /tmp/out/approval_request.json \
      --decision rescope --by "Team lead" --at 2026-10-25T10:00:00-06:00 \
      --rescoped-issue issues/tier1.json --mock --out /tmp/resumed-out

  # or close it without running anything:
  python3 run_resume.py --repo ../hackathon-demo-repo \
      --request /tmp/out/approval_request.json \
      --decision reject --by "Team lead" --at 2026-10-25T10:00:00-06:00 \
      --mock --out /tmp/closed-out

Exit codes: 0 = resumed and passed, or closed by human decision;
1 = resumed but not PR-ready; 2 = rescoped issue escalated again
(the guardrail re-checks every rescoped issue before any model call).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from daas import approval, pipeline  # noqa: E402
from daas.llm import default_client  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--request", required=True, help="approval_request.json from an escalation")
    ap.add_argument("--decision", required=True, choices=list(approval.DECISIONS))
    ap.add_argument("--by", required=True, dest="decided_by")
    ap.add_argument("--at", required=True, dest="decided_at")
    ap.add_argument("--notes", default=None)
    ap.add_argument("--rescoped-issue", default=None,
                    help="issue JSON file; required for --decision rescope")
    ap.add_argument("--out", required=True)
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()

    request = json.loads(Path(args.request).read_text())
    rescoped = None
    if args.rescoped_issue:
        rescoped = json.loads(Path(args.rescoped_issue).read_text())
    decided = approval.record_decision(
        request, args.decision, args.decided_by, args.decided_at,
        notes=args.notes, rescoped_issue=rescoped)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "approval_request.json").write_text(approval.to_json(decided))
    (out / "escalation.md").write_text(approval.render_markdown(decided))

    client = default_client(mock=args.mock)
    try:
        result = pipeline.resume(args.repo, decided, client, out)
    except pipeline.Escalation as e:
        print(f"RE-ESCALATED: rescoped issue blocked again: {e.reason}")
        return 2
    print(json.dumps(result, indent=2))
    if not result.get("resumed"):
        return 0
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
