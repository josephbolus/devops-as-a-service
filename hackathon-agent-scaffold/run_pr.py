#!/usr/bin/env python3
"""Full agent loop against a real git repo: branch -> pipeline -> PR.

Usage:
  python3 run_pr.py --repo ../hackathon-demo-repo --issue issues/tier1.json \
      --out /tmp/daas-pr [--mock] [--base main]

Flow: refuse a dirty target -> create branch daas/<issue-slug> -> run the
pipeline in place -> on pass, commit the changed files, push the branch,
and open the PR with the pipeline's pr_body.md. On a failed review or
failing tests, the branch stays local and no PR is opened (exit 1).
Guardrail escalation: nothing is touched (exit 2).

The work lives in run() so the demo console (demo_ui.py) can drive the
same flow in-process, stream stage events via on_event, and read the
opened PR's URL from the returned dict.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from daas import pipeline  # noqa: E402
from daas.llm import default_client  # noqa: E402


def git(repo, *args, check=True):
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def slugify(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "issue"


def run(repo, issue, out, base="main", mock=False, on_event=None):
    """Drive the full branch -> pipeline -> PR flow once.

    Returns {"exit": int, "pr_url": str|None, "result": dict|None,
    "branch": str}. Exit codes match the CLI: 0 PR opened, 1 not
    PR-ready / PR creation failed, 2 escalated, 3 dirty target.
    """
    repo = Path(repo).resolve()
    out = Path(out)
    branch = f"daas/{slugify(issue['title'])}"
    outcome = {"exit": 0, "pr_url": None, "result": None, "branch": branch}

    dirty = git(repo, "status", "--porcelain", "--", ".").stdout.strip()
    if dirty:
        print(f"ABORT: target repo has uncommitted changes:\n{dirty}")
        outcome["exit"] = 3
        return outcome
    git(repo, "checkout", "-b", branch)

    client = default_client(mock=mock)
    try:
        result = pipeline.run(repo, issue, client, out, on_event=on_event)
    except pipeline.Escalation as e:
        git(repo, "checkout", base)
        git(repo, "branch", "-D", branch)
        print(f"ESCALATED: {e.reason} (see {out}/escalation.md)")
        outcome["exit"] = 2
        return outcome
    outcome["result"] = result

    print(json.dumps(result, indent=2))
    if not result["passed"]:
        print(f"NOT PR-READY: branch {branch} left local for inspection.")
        outcome["exit"] = 1
        return outcome

    for name in result["changed"]:
        git(repo, "add", "--", name)
    git(repo, "-c", "user.name=daas-agent", "-c", "user.email=daas-agent@localhost",
        "commit", "-m", f"daas: {issue['title']}")
    git(repo, "push", "-u", "origin", branch)
    body = Path(out, "pr_body.md").read_text()
    proc = subprocess.run(
        ["gh", "pr", "create", "--title", issue["title"], "--body", body,
         "--base", base, "--head", branch],
        cwd=repo, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"PR creation failed: {proc.stderr.strip()}")
        outcome["exit"] = 1
        return outcome
    outcome["pr_url"] = proc.stdout.strip()
    print(f"PR OPENED: {outcome['pr_url']}")
    return outcome


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--issue", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", default="main")
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()

    issue = json.loads(Path(args.issue).read_text())
    outcome = run(args.repo, issue, args.out, base=args.base, mock=args.mock)
    return outcome["exit"]


if __name__ == "__main__":
    raise SystemExit(main())
