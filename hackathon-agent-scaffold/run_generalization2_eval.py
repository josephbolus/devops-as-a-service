#!/usr/bin/env python3
"""Generalization eval 2: run the pipeline LIVE on a third, unseen codebase.

Usage:
  python3 run_generalization_eval.py [--out ../eval-scorecard/generalization-runs.json]

Question (maximizer new-feature backlog item 1, Oct 25): every live
result so far is on the seeded demo repo (hackathon-demo-repo) whose
issues the scaffold grew up with. Does the pipeline generalize to a
codebase it has never seen — a different package (`textkit`), a
different domain (text tokens/slugs/reading stats), a different module
layout — vendored under ../generalization2/ with its own test suite
and a genuine pre-existing bug (first_words slices words[:n+1] and
returns one word more than requested)?

Method: identical to the other live evals — pipeline.run against a
fresh git-initialized COPY of ../generalization/ (the vendored copy is
never run in place and was not tuned after the run), ConnectorClient
(Meta Model API via the custom.meta-model-api connector, no env key),
kept split config (CODER/REVIEWER=muse-wonder-1.0,
TRIAGE/PLANNER=muse-spark-1.3), wall clock = pipeline duration,
model actually used recorded per call, pr_body and diff captured.
One run, reported honestly whatever the outcome.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from daas import pipeline  # noqa: E402
from daas.llm import ConnectorClient, resolve_model  # noqa: E402

HERE = Path(__file__).parent
ROOT = HERE.parent
GEN_REPO = ROOT / "generalization2"
ISSUE_FILE = GEN_REPO / "issue.json"
SPLIT_ROLE_MODELS = {"CODER": "muse-wonder-1.0",
                     "REVIEWER": "muse-wonder-1.0"}
DEFAULT_MODEL = "muse-spark-1.3"
CONFIG_LABEL = ("split (kept config): CODER/REVIEWER=muse-wonder-1.0, "
                "TRIAGE/PLANNER=muse-spark-1.3")


class RecordingClient:
    """ConnectorClient wrapper recording the model used per call."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    def complete_json(self, system, user):
        role = system.strip().split()[0].upper()
        model = resolve_model(system, self.inner.model,
                              self.inner.role_models)
        self.calls.append({"role": role, "model": model})
        return self.inner.complete_json(system, user)


def run_one(client_factory):
    issue = json.loads(ISSUE_FILE.read_text())
    row = {"slug": "generalization2-first-words", "issue": issue["title"],
           "mode": "live-split-generalization2",
           "target_codebase": "generalization2/ (textkit package)"}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        repo = tmp / "repo"
        shutil.copytree(GEN_REPO, repo,
                        ignore=shutil.ignore_patterns("__pycache__"))
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.email=eval@local",
                        "-c", "user.name=eval", "commit", "-qm", "base"],
                       cwd=repo, check=True)
        client = client_factory()
        events = {}
        started = datetime.now(timezone.utc)
        t0 = time.perf_counter()
        try:
            result = pipeline.run(repo, issue, client, tmp / "out",
                                  on_event=lambda e: events.update(
                                      {e["stage"]: e["data"]}))
        except pipeline.Escalation as e:
            wall = round(time.perf_counter() - t0, 2)
            row.update({"outcome": "escalated", "correct": False,
                        "reason": e.reason, "tests_before": None,
                        "tests_after": None, "files_touched": [],
                        "unexpected_files": [], "wall_clock_seconds": wall,
                        "model_calls": len(client.calls),
                        "models_by_role": {}, "pr_produced": False})
            return row, started
        except Exception as e:  # a failed live run is a measured result
            wall = round(time.perf_counter() - t0, 2)
            row.update({"outcome": "failed", "correct": False,
                        "error": f"{type(e).__name__}: {e}"[:500],
                        "tests_before": None, "tests_after": None,
                        "files_touched": [], "unexpected_files": [],
                        "wall_clock_seconds": wall,
                        "model_calls": len(client.calls),
                        "models_by_role": {c["role"]: c["model"]
                                           for c in client.calls},
                        "pr_produced": False})
            return row, started
        wall = round(time.perf_counter() - t0, 2)
        review = events.get("review", {})
        code = events.get("code", {})
        pr_body_path = tmp / "out" / "pr_body.md"
        row.update({
            "outcome": "passed" if result["passed"] else "failed",
            "correct": bool(result["passed"]),
            "tests_before": result["tests_before"],
            "tests_after": result["tests_after"],
            "files_touched": sorted(set(result["changed"])),
            "unexpected_files": result["unexpected_files"],
            "wall_clock_seconds": wall,
            "model_calls": len(client.calls),
            "models_by_role": {c["role"]: c["model"] for c in client.calls},
            "tests_ok": result["tests_ok"],
            "reviewer_verdict": review.get("verdict"),
            "reviewer_notes": review.get("notes", ""),
            "pr_produced": bool(result["passed"]),
            "cost": result.get("cost"),
            "pr_body": pr_body_path.read_text() if pr_body_path.exists() else "",
            "diff": code.get("diff", ""),
        })
        return row, started


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "eval-scorecard"
                                         / "generalization2-runs.json"))
    args = ap.parse_args()

    def factory():
        return RecordingClient(ConnectorClient(
            model=DEFAULT_MODEL, role_models=dict(SPLIT_ROLE_MODELS)))

    row, started = run_one(factory)
    row["started_at"] = started.isoformat()
    passed = row["outcome"] == "passed"
    doc = {
        "record": "Generalization eval 2 — DevOps as a Service, Oct 25, 2026 "
                  "(maximizer iteration 19: second generalization target)",
        "method": "pipeline.run (guardrail -> triage -> plan -> code -> "
                  "tests -> review) against a fresh git-initialized copy "
                  "of generalization2/ (textkit), ConnectorClient (Meta "
                  "Model API via custom.meta-model-api connector, no env "
                  "key), kept split config. The vendored target was "
                  "created for this run, never previously run, and was "
                  "not tuned after the run.",
        "config": CONFIG_LABEL,
        "target": {
            "codebase": "generalization/",
            "package": "textkit",
            "differs_from_seeded_demo_repo": [
                "package name textkit/ vs the demo repo's app/ and ledgerlite/",
                "domain: text normalization/tokens/slugs/reading stats vs "
                "pagination, HTTP retry, CLI report and ledger amounts",
                "module layout: normalize/tokens/slug/counts vs "
                "pagination/http_client/cli/report",
                "baseline suite 10 tests (demo repo baseline: 6, ledgerlite: 9)",
                "no MockClient canned response exists for this issue — "
                "the live models had no scaffold-provided answer",
            ],
        },
        "runs": [row],
        "summary": {
            "passed": passed,
            "outcome": row["outcome"],
            "tests_before": row.get("tests_before"),
            "tests_after": row.get("tests_after"),
            "test_growth": ((row["tests_after"] - row["tests_before"])
                            if row.get("tests_after") is not None
                            and row.get("tests_before") is not None
                            else None),
            "wall_clock_seconds": row["wall_clock_seconds"],
            "files_touched": row.get("files_touched", []),
            "unexpected_files": row.get("unexpected_files", []),
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"generalization: {row['outcome']} wall={row['wall_clock_seconds']}s "
          f"tests={row.get('tests_before')}->{row.get('tests_after')} "
          f"files={row.get('files_touched')}")
    print(f"summary: {doc['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
