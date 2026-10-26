#!/usr/bin/env python3
"""Generalization eval 3: run the pipeline LIVE on a fourth, unseen codebase.

Usage:
  python3 run_generalization3_eval.py [--out ../eval-scorecard/generalization3-runs.json]

Question (maximizer iteration 23, item-4 polish): both earlier
generalization runs were single-defect, single-production-file fixes
on unseen codebases. Does the pipeline generalize to an unseen
codebase whose issue carries TWO defects in TWO different production
modules (gradebook/averages.py weighted_mean divides by len(values)
instead of the sum of the weights; gradebook/letters.py letter_grade
uses > 90 instead of >= 90) — so the planner must name both files
and the coder must fix both?

Method: identical to the other live evals — pipeline.run against a
fresh git-initialized COPY of ../generalization3/ (the vendored copy
is never run in place and was not tuned after the run),
ConnectorClient (Meta Model API via the custom.meta-model-api
connector, no env key), kept split config (CODER/REVIEWER=
muse-wonder-1.0, TRIAGE/PLANNER=muse-spark-1.3), wall clock =
pipeline duration, model actually used recorded per call, pr_body
and diff captured. One run, reported honestly whatever the outcome.

Independent probe: after pipeline.run finishes, checks written for
this evaluation (NOT by the pipeline and NOT part of its regression
tests) import the fixed copy's gradebook package and verify both
defects and both end-to-end combinations. The run only counts as
passed if the pipeline passes AND every probe check passes — the
pipeline's own added tests are not the only evidence.
"""
import argparse
import importlib
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
GEN_REPO = ROOT / "generalization3"
ISSUE_FILE = GEN_REPO / "issue.json"
SPLIT_ROLE_MODELS = {"CODER": "muse-wonder-1.0",
                     "REVIEWER": "muse-wonder-1.0"}
DEFAULT_MODEL = "muse-spark-1.3"
CONFIG_LABEL = ("split (kept config): CODER/REVIEWER=muse-wonder-1.0, "
                "TRIAGE/PLANNER=muse-spark-1.3")
PRODUCTION_FILES = ["gradebook/averages.py", "gradebook/letters.py"]


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


def run_probe(repo):
    """Independent checks against the (possibly fixed) copy at `repo`.

    Returns a list of {check, expected, actual, passed}. Written for
    this evaluation; the pipeline never sees them.
    """
    for name in list(sys.modules):
        if name == "gradebook" or name.startswith("gradebook."):
            del sys.modules[name]
    sys.path.insert(0, str(repo))
    try:
        averages = importlib.import_module("gradebook.averages")
        letters = importlib.import_module("gradebook.letters")
        report = importlib.import_module("gradebook.report")
        cases = [
            ("weighted_mean([80, 100], [3, 1])", 85.0,
             averages.weighted_mean([80, 100], [3, 1])),
            ("weighted_mean([70, 90], [1, 3])", 85.0,
             averages.weighted_mean([70, 90], [1, 3])),
            ("weighted_mean([80, 100], [1, 1]) (unchanged case)", 90.0,
             averages.weighted_mean([80, 100], [1, 1])),
            ("letter_grade(90)", "A", letters.letter_grade(90)),
            ("letter_grade(89.9)", "B", letters.letter_grade(89.9)),
            ("letter_grade(95) (unchanged case)", "A",
             letters.letter_grade(95)),
            ("final_letter([90, 90], [1, 1])", "A",
             report.final_letter([90, 90], [1, 1])),
            ("final_letter([80, 100], [3, 1])", "B",
             report.final_letter([80, 100], [3, 1])),
        ]
        return [{"check": name, "expected": expected, "actual": actual,
                 "passed": actual == expected}
                for name, expected, actual in cases]
    finally:
        sys.path.remove(str(repo))


def run_one(client_factory):
    issue = json.loads(ISSUE_FILE.read_text())
    row = {"slug": "generalization3-two-defects", "issue": issue["title"],
           "mode": "live-split-generalization3",
           "target_codebase": "generalization3/ (gradebook package)"}
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
            row.update({"outcome": "escalated", "pipeline_outcome": "escalated",
                        "correct": False, "reason": e.reason,
                        "tests_before": None, "tests_after": None,
                        "files_touched": [], "unexpected_files": [],
                        "production_files_touched": [],
                        "wall_clock_seconds": wall,
                        "model_calls": len(client.calls),
                        "models_by_role": {}, "pr_produced": False,
                        "probe": run_probe(repo),
                        "probe_passed": False})
            return row, started
        except Exception as e:  # a failed live run is a measured result
            wall = round(time.perf_counter() - t0, 2)
            row.update({"outcome": "failed", "pipeline_outcome": "failed",
                        "correct": False,
                        "error": f"{type(e).__name__}: {e}"[:500],
                        "tests_before": None, "tests_after": None,
                        "files_touched": [], "unexpected_files": [],
                        "production_files_touched": [],
                        "wall_clock_seconds": wall,
                        "model_calls": len(client.calls),
                        "models_by_role": {c["role"]: c["model"]
                                           for c in client.calls},
                        "pr_produced": False,
                        "probe": run_probe(repo),
                        "probe_passed": False})
            return row, started
        wall = round(time.perf_counter() - t0, 2)
        review = events.get("review", {})
        code = events.get("code", {})
        pr_body_path = tmp / "out" / "pr_body.md"
        probe = run_probe(repo)
        probe_passed = all(c["passed"] for c in probe)
        pipeline_passed = bool(result["passed"])
        touched = sorted(set(result["changed"]))
        outcome = ("passed" if pipeline_passed and probe_passed
                   else "partial" if pipeline_passed or probe_passed
                   else "failed")
        row.update({
            "outcome": outcome,
            "pipeline_outcome": "passed" if pipeline_passed else "failed",
            "correct": bool(pipeline_passed and probe_passed),
            "tests_before": result["tests_before"],
            "tests_after": result["tests_after"],
            "files_touched": touched,
            "production_files_touched": [f for f in touched
                                          if f in PRODUCTION_FILES],
            "unexpected_files": result["unexpected_files"],
            "wall_clock_seconds": wall,
            "model_calls": len(client.calls),
            "models_by_role": {c["role"]: c["model"] for c in client.calls},
            "tests_ok": result["tests_ok"],
            "reviewer_verdict": review.get("verdict"),
            "reviewer_notes": review.get("notes", ""),
            "pr_produced": bool(result["passed"]),
            "cost": result.get("cost"),
            "probe": probe,
            "probe_passed": probe_passed,
            "pr_body": pr_body_path.read_text() if pr_body_path.exists() else "",
            "diff": code.get("diff", ""),
        })
        return row, started


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "eval-scorecard"
                                         / "generalization3-runs.json"))
    args = ap.parse_args()

    def factory():
        return RecordingClient(ConnectorClient(
            model=DEFAULT_MODEL, role_models=dict(SPLIT_ROLE_MODELS)))

    row, started = run_one(factory)
    row["started_at"] = started.isoformat()
    passed = row["outcome"] == "passed"
    doc = {
        "record": "Generalization eval 3 — DevOps as a Service, Oct 25, 2026 "
                  "(maximizer iteration 23: multi-file generalization target)",
        "method": "pipeline.run (guardrail -> triage -> plan -> code -> "
                  "tests -> review) against a fresh git-initialized copy "
                  "of generalization3/ (gradebook), ConnectorClient (Meta "
                  "Model API via custom.meta-model-api connector, no env "
                  "key), kept split config, plus an independent probe of "
                  "both defects run against the fixed copy afterwards. "
                  "The vendored target was created for this run, never "
                  "previously run, and was not tuned after the run.",
        "config": CONFIG_LABEL,
        "target": {
            "codebase": "generalization3/",
            "package": "gradebook",
            "differs_from_earlier_codebases": [
                "package name gradebook/ vs the demo repo's app/, "
                "ledgerlite/ and textkit/",
                "domain: course grading (weighted means, letter grades, "
                "grade reports) vs pagination/HTTP/CLI, ledger amounts "
                "and text tokens/slugs",
                "module layout: averages/letters/report vs the other "
                "codebases' layouts",
                "baseline suite 12 tests (demo repo: 6, ledgerlite: 9, "
                "textkit: 10)",
                "TWO defects in TWO production modules "
                "(gradebook/averages.py and gradebook/letters.py) — "
                "every earlier live fix touched exactly one production "
                "file",
                "no MockClient canned response exists for this issue — "
                "the live models had no scaffold-provided answer",
            ],
        },
        "runs": [row],
        "summary": {
            "passed": passed,
            "outcome": row["outcome"],
            "pipeline_outcome": row["pipeline_outcome"],
            "probe_passed": row["probe_passed"],
            "tests_before": row.get("tests_before"),
            "tests_after": row.get("tests_after"),
            "test_growth": ((row["tests_after"] - row["tests_before"])
                            if row.get("tests_after") is not None
                            and row.get("tests_before") is not None
                            else None),
            "wall_clock_seconds": row["wall_clock_seconds"],
            "files_touched": row.get("files_touched", []),
            "production_files_touched": row.get("production_files_touched", []),
            "unexpected_files": row.get("unexpected_files", []),
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"generalization3: {row['outcome']} "
          f"(pipeline={row['pipeline_outcome']}, probe={row['probe_passed']}) "
          f"wall={row['wall_clock_seconds']}s "
          f"tests={row.get('tests_before')}->{row.get('tests_after')} "
          f"files={row.get('files_touched')}")
    print(f"summary: {doc['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
