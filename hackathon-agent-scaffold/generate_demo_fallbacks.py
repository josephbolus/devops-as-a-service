#!/usr/bin/env python3
"""Generate the demo recording-fallback package (mock end-states).

Usage:
  python3 generate_demo_fallbacks.py [--out ../demo-fallbacks]

The demo script's fallbacks promise a walkable end state if a live run
fails on recording day. This script produces that end state for the
mock runs: for each seeded issue it runs the pipeline against a COPY
of the demo repo and writes, per issue, into <out>/mock/<slug>/:

  pr_body.md   (or escalation.md for the guardrail issue)
  result.json  (pipeline result: passed, test counts, changed files)
  diff.patch   (unified diff of the changed files vs the pristine copy)

Plus <out>/mock/manifest.json summarising every run.

These are MOCK runs (deterministic MockClient) and are labeled as such.
The live end state (a real Meta API run that opened a real PR) lives
under <out>/live/ and is captured separately — this script never
touches it, so regenerating the mock package cannot overwrite the
live evidence.
"""
import argparse
import difflib
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from daas import pipeline  # noqa: E402
from daas.llm import MockClient  # noqa: E402

HERE = Path(__file__).parent
DEMO_REPO = HERE.parent / "hackathon-demo-repo"
ISSUES = [("tier1", "tier1.json"), ("tier2", "tier2.json"),
          ("tier3", "tier3.json"), ("guardrail", "guardrail.json")]


def _snapshot(repo):
    return {str(p.relative_to(repo)): p.read_text()
            for p in sorted(repo.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


def _diff(before, repo, changed):
    out = []
    for name in sorted(set(changed)):
        old = before.get(name, "")
        new = (repo / name).read_text() if (repo / name).is_file() else ""
        out.extend(difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile=f"a/{name}", tofile=f"b/{name}"))
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE.parent / "demo-fallbacks"))
    args = ap.parse_args()
    mock_out = Path(args.out) / "mock"
    if mock_out.exists():
        shutil.rmtree(mock_out)
    mock_out.mkdir(parents=True)

    manifest = {"mode": "mock", "client": "MockClient (deterministic, offline)",
                "runs": []}
    for slug, issue_file in ISSUES:
        issue = json.loads((HERE / "issues" / issue_file).read_text())
        dest = mock_out / slug
        dest.mkdir()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            shutil.copytree(DEMO_REPO, repo,
                            ignore=shutil.ignore_patterns("__pycache__"))
            before = _snapshot(repo)
            try:
                result = pipeline.run(repo, issue, MockClient(), dest)
            except pipeline.Escalation as e:
                (dest / "result.json").write_text(json.dumps({
                    "issue": issue["title"], "escalated": True,
                    "reason": e.reason, "passed": False}, indent=2) + "\n")
                manifest["runs"].append({
                    "slug": slug, "issue": issue["title"],
                    "escalated": True, "passed": False})
                continue
            result = dict(result)
            result["issue"] = issue["title"]
            result["changed_unique"] = sorted(set(result["changed"]))
            (dest / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            (dest / "diff.patch").write_text(_diff(before, repo, result["changed"]))
            manifest["runs"].append({
                "slug": slug, "issue": issue["title"], "escalated": False,
                "passed": result["passed"],
                "tests_before": result["tests_before"],
                "tests_after": result["tests_after"],
                "changed": result["changed_unique"],
                "unexpected_files": result["unexpected_files"]})
    (mock_out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    return 0 if all(r["passed"] or r["escalated"] for r in manifest["runs"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
