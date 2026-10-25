"""Pipeline: issue in -> triage -> planner -> coder -> tests -> reviewer -> PR body out.

The pipeline itself stops at a written PR body (pr_body.md) plus the list
of changed files, so the whole loop is testable offline with no GitHub
side effects. run_pr.py wraps it with the real branch/commit/PR steps.
The agents receive real context: the planner sees the repo file tree,
the coder sees the current contents of the planned files (its edits
must quote them verbatim), and the reviewer sees the actual diff.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from . import guardrail
from . import prompts


class Escalation(RuntimeError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _repo_tree(repo: Path):
    """Repo-relative file paths, skipping noise — the planner's map."""
    skip = {".git", "__pycache__", ".pytest_cache"}
    out = []
    for p in sorted(repo.rglob("*")):
        if p.is_file() and not any(part in skip for part in p.parts):
            out.append(str(p.relative_to(repo)))
    return out


def _file_contents(repo: Path, files):
    """Current contents of the planned files that already exist."""
    out = {}
    for name in files:
        path = repo / name
        if path.is_file():
            out[name] = path.read_text()
    return out


def _diff(repo: Path, changed):
    """Unified diff of the changed files when the repo is under git.

    `git diff` never shows untracked files, and the coder's regression
    test is usually a brand-new file — synthesize a new-file block for
    those so the reviewer can actually verify the coverage.
    """
    proc = subprocess.run(["git", "-C", str(repo), "diff", "--", *changed],
                          capture_output=True, text=True, cwd=str(repo))
    out = proc.stdout if proc.returncode == 0 else ""
    listed = subprocess.run(["git", "-C", str(repo), "ls-files", "--", *changed],
                            capture_output=True, text=True, cwd=str(repo))
    tracked = set(listed.stdout.split()) if listed.returncode == 0 else set()
    for name in changed:
        path = repo / name
        if name not in tracked and path.is_file():
            body = "".join(f"+{line}\n" for line in path.read_text().splitlines())
            out += f"\n--- new file: {name} ---\n{body}"
    return out


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
    log = (proc.stdout + proc.stderr).strip()
    m = re.search(r"Ran (\d+) test", log)
    return proc.returncode == 0, log, int(m.group(1)) if m else 0


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

    triage = client.complete_json(prompts.TRIAGE, json.dumps(issue))
    plan = client.complete_json(prompts.PLANNER,
                                json.dumps({"issue": issue, "triage": triage,
                                            "repo_tree": _repo_tree(repo)}))
    _, _, tests_before = _run_tests(repo)
    coder = client.complete_json(prompts.CODER,
                                 json.dumps({"issue": issue, "plan": plan,
                                             "files": _file_contents(
                                                 repo, plan.get("expected_files", []))}))
    changed = _apply_edits(repo, coder["edits"])

    tests_ok, test_log, tests_after = _run_tests(repo)
    review = client.complete_json(prompts.REVIEWER,
                                  json.dumps({"changed": changed, "tests_ok": tests_ok,
                                              "tests_before": tests_before,
                                              "tests_after": tests_after,
                                              "diff": _diff(repo, changed)}))

    unexpected = sorted(set(changed) - set(plan.get("expected_files", changed)))
    test_files_changed = [f for f in changed if "/test" in f or f.startswith("test")]
    # A changed test file only counts as coverage if tests actually ran:
    # the discovered-test count must grow past the pre-fix baseline.
    coverage_live = not test_files_changed or tests_after > tests_before
    passed = tests_ok and coverage_live and review.get("verdict") == "approve" and not unexpected
    pr_body = (
        f"## {triage['summary']}\n\n"
        f"Closes: {issue['title']}\n\n"
        f"### Plan\n" + "\n".join(f"- {s}" for s in plan["steps"]) + "\n\n"
        f"### Files changed\n" + "\n".join(f"- {f}" for f in changed) + "\n\n"
        f"### Tests\n{'All tests pass' if tests_ok else 'TESTS FAILING — see log'} "
        f"({tests_before} → {tests_after} discovered).\n\n"
        f"### Reviewer\n{review.get('verdict')}: {review.get('notes', '')}\n")
    (out_dir / "pr_body.md").write_text(pr_body)
    return {"passed": passed, "changed": changed, "tests_ok": tests_ok,
            "tests_before": tests_before, "tests_after": tests_after,
            "unexpected_files": unexpected, "test_log_tail": test_log[-400:]}
