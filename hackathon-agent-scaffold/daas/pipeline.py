"""Pipeline: issue in -> triage -> planner -> coder -> tests -> reviewer -> PR body out.

The PR step stops at a written PR body (pr_body.md) plus the list of
changed files. Actually opening the PR is one `gh pr create` on Day 0
once the repo choice is made; keeping it out of the scaffold means the
whole loop is testable offline today, with no GitHub side effects.
"""
import json
import subprocess
import sys
from pathlib import Path

from . import guardrail


class Escalation(RuntimeError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _apply_edits(repo: Path, edits):
    changed = []
    for edit in edits:
        path = repo / edit["file"]
        if edit["old"] is None:  # create new file
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(edit["new"])
        else:
            text = path.read_text()
            if edit["old"] not in text:
                raise RuntimeError(f"Coder edit does not apply cleanly to {edit['file']}")
            path.write_text(text.replace(edit["old"], edit["new"], 1))
        changed.append(edit["file"])
    return changed


def _run_tests(repo: Path):
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
        cwd=repo, capture_output=True, text=True)
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def run(repo, issue, client, out_dir):
    """issue: dict with title/body. Returns result dict; raises Escalation."""
    repo = Path(repo)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    blocked, reason = guardrail.check(issue["title"], issue.get("body", ""))
    if blocked:
        summary = (f"ESCALATED — no PR opened.\nIssue: {issue['title']}\n"
                   f"Reason: {reason}.\nThis request needs an explicit human decision.")
        (out_dir / "escalation.md").write_text(summary)
        raise Escalation(reason)

    triage = client.complete_json("TRIAGE agent: classify the GitHub issue as JSON.",
                                  json.dumps(issue))
    plan = client.complete_json("PLANNER agent: plan the fix as JSON.",
                                json.dumps({"issue": issue, "triage": triage}))
    coder = client.complete_json("CODER agent: return file edits as JSON.",
                                 json.dumps({"issue": issue, "plan": plan}))
    changed = _apply_edits(repo, coder["edits"])

    tests_ok, test_log = _run_tests(repo)
    review = client.complete_json("REVIEWER agent: review the diff as JSON.",
                                  json.dumps({"changed": changed, "tests_ok": tests_ok}))

    unexpected = sorted(set(changed) - set(plan.get("expected_files", changed)))
    passed = tests_ok and review.get("verdict") == "approve" and not unexpected
    pr_body = (
        f"## {triage['summary']}\n\n"
        f"Closes: {issue['title']}\n\n"
        f"### Plan\n" + "\n".join(f"- {s}" for s in plan["steps"]) + "\n\n"
        f"### Files changed\n" + "\n".join(f"- {f}" for f in changed) + "\n\n"
        f"### Tests\n{'All tests pass.' if tests_ok else 'TESTS FAILING — see log.'}\n\n"
        f"### Reviewer\n{review.get('verdict')}: {review.get('notes', '')}\n")
    (out_dir / "pr_body.md").write_text(pr_body)
    return {"passed": passed, "changed": changed, "tests_ok": tests_ok,
            "unexpected_files": unexpected, "test_log_tail": test_log[-400:]}
