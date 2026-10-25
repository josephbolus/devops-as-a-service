#!/usr/bin/env python3
"""Per-role model split experiment: the former Day-1 decision, measured.

Usage:
  python3 run_split_eval.py [--out ../eval-scorecard/split-runs.json]

Question: does a per-role split beat the uniform configuration that
produced the Oct 25 live eval (eval-scorecard/live-runs.json)?

Split under test (via the existing DAAS_MODEL_<ROLE> mechanism,
resolved in daas/llm.py before the call):
  CODER    -> muse-wonder-1.0   (Meta's most capable model on the
                                 Model API; availability probed live
                                 through the connector before this run)
  REVIEWER -> muse-wonder-1.0
  TRIAGE   -> muse-spark-1.3    (default, unchanged)
  PLANNER  -> muse-spark-1.3    (default, unchanged)

Method: identical to the uniform live eval — pipeline.run per seeded
issue (Tier 1/2/3 + guardrail) against a fresh git-initialized copy of
hackathon-demo-repo, ConnectorClient (Meta Model API via the
custom.meta-model-api connector, no env key), wall clock = pipeline
duration, reviewer verdict/notes captured via on_event, the model
actually used per role recorded via resolve_model on every call.

DECISION RULE — registered here BEFORE any split run was made:
  1. Pass count first: work tiers passed + guardrail correct.
  2. Then total discovered-test growth across the work tiers (more
     passing regression coverage is better, only among passed runs).
  3. Then total wall clock (faster is better).
  The split is kept only if it wins on (1), or ties (1) and wins on
  (2), or ties (1)-(2) and wins on (3). Any other outcome keeps the
  uniform configuration — which is also the cheaper one per token at
  published rates (Wonder is the premium tier), so a full tie keeps
  uniform. No post-hoc criteria.
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
DEMO_REPO = ROOT / "hackathon-demo-repo"
BASELINE = ROOT / "eval-scorecard" / "live-runs.json"
ISSUES = [("tier1", "tier1.json"), ("tier2", "tier2.json"),
          ("tier3", "tier3.json"), ("guardrail", "guardrail.json")]

SPLIT_ROLE_MODELS = {"CODER": "muse-wonder-1.0",
                     "REVIEWER": "muse-wonder-1.0"}
DEFAULT_MODEL = "muse-spark-1.3"
DECISION_RULE = (
    "1) pass count (work tiers + guardrail correct); "
    "2) total discovered-test growth across work tiers; "
    "3) total wall clock (lower wins). Split kept only if it wins "
    "on (1), or ties (1) and wins on (2), or ties (1)-(2) and wins "
    "on (3); a full tie keeps uniform (also cheaper per token).")


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


def _summary(runs):
    work = [r for r in runs if r["slug"] != "guardrail"]
    guard = [r for r in runs if r["slug"] == "guardrail"]
    passed = sum(1 for r in work if r["outcome"] == "passed")
    growth = sum((r["tests_after"] or 0) - (r["tests_before"] or 0)
                 for r in work if r["outcome"] == "passed")
    return {
        "work_tiers_passed": f"{passed}/{len(work)}",
        "pass_count": passed + sum(1 for r in guard if r["correct"]),
        "guardrail_escalated": bool(guard and guard[0]["correct"]),
        "total_test_growth": growth,
        "total_wall_clock_seconds": round(
            sum(r["wall_clock_seconds"] for r in runs), 2),
    }


def decide(baseline_summary, split_summary):
    """The pre-registered decision rule, as a pure function."""
    for key, split_better in (
            ("pass_count", lambda a, b: b > a),
            ("total_test_growth", lambda a, b: b > a),
            ("total_wall_clock_seconds", lambda a, b: b < a)):
        a, b = baseline_summary[key], split_summary[key]
        if split_better(a, b):
            return {"keep": "split", "decided_on": key,
                    "baseline_value": a, "split_value": b}
        if b != a:
            return {"keep": "uniform", "decided_on": key,
                    "baseline_value": a, "split_value": b}
    return {"keep": "uniform", "decided_on": "full tie",
            "baseline_value": None, "split_value": None}


def _run_one(slug, issue_file, client_factory):
    issue = json.loads((HERE / "issues" / issue_file).read_text())
    row = {"slug": slug, "issue": issue["title"], "mode": "live-split"}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        repo = tmp / "repo"
        shutil.copytree(DEMO_REPO, repo,
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
            row.update({"outcome": "escalated",
                        "correct": slug == "guardrail",
                        "reason": e.reason, "tests_before": None,
                        "tests_after": None, "files_touched": [],
                        "unexpected_files": [], "wall_clock_seconds": wall,
                        "model_calls": len(client.calls),
                        "models_by_role": {}, "pr_produced": False,
                        "approval_request_written":
                            (tmp / "out"
                             / "approval_request.json").exists()})
            return row, started, wall
        except Exception as e:  # a failed live run is a measured result
            wall = round(time.perf_counter() - t0, 2)
            row.update({"outcome": "failed", "correct": False,
                        "error": f"{type(e).__name__}: {e}"[:300],
                        "tests_before": None, "tests_after": None,
                        "files_touched": [], "unexpected_files": [],
                        "wall_clock_seconds": wall,
                        "model_calls": len(client.calls),
                        "models_by_role": {c["role"]: c["model"]
                                           for c in client.calls},
                        "pr_produced": False})
            return row, started, wall
        wall = round(time.perf_counter() - t0, 2)
        review = events.get("review", {})
        row.update({
            "outcome": "passed" if result["passed"] else "failed",
            "correct": bool(result["passed"]),
            "tests_before": result["tests_before"],
            "tests_after": result["tests_after"],
            "files_touched": sorted(set(result["changed"])),
            "unexpected_files": result["unexpected_files"],
            "wall_clock_seconds": wall,
            "model_calls": len(client.calls),
            "models_by_role": {c["role"]: c["model"]
                               for c in client.calls},
            "tests_ok": result["tests_ok"],
            "reviewer_verdict": review.get("verdict"),
            "reviewer_notes": review.get("notes", ""),
            "pr_produced": bool(result["passed"]),
        })
        return row, started, wall


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "eval-scorecard"
                                         / "split-runs.json"))
    args = ap.parse_args()

    def factory():
        return RecordingClient(ConnectorClient(
            model=DEFAULT_MODEL, role_models=dict(SPLIT_ROLE_MODELS)))

    runs = []
    for slug, f in ISSUES:
        row, started, _ = _run_one(slug, f, factory)
        row["started_at"] = started.isoformat()
        runs.append(row)
        print(f"{slug}: {row['outcome']} "
              f"wall={row['wall_clock_seconds']}s "
              f"models={row.get('models_by_role')}", flush=True)

    baseline_doc = json.loads(BASELINE.read_text())
    baseline_runs = baseline_doc["runs"]
    # Baseline summary in the same shape _summary produces.
    b_work = [r for r in baseline_runs if r["slug"] != "guardrail"]
    b_guard = [r for r in baseline_runs if r["slug"] == "guardrail"][0]
    baseline_summary = {
        "work_tiers_passed": baseline_doc["summary"]["work_tiers_passed"],
        "pass_count": sum(1 for r in b_work if r["correct"])
                      + (1 if b_guard["correct"] else 0),
        "guardrail_escalated": bool(b_guard["correct"]),
        "total_test_growth": sum(r["tests_after"] - r["tests_before"]
                                 for r in b_work if r["correct"]),
        "total_wall_clock_seconds":
            baseline_doc["summary"]["total_wall_clock_seconds"],
    }
    split_summary = _summary(runs)
    decision = decide(baseline_summary, split_summary)
    doc = {
        "record": "Per-role model split experiment — DevOps as a "
                  "Service, Oct 25, 2026 (maximizer iteration 11)",
        "method": "Same as eval-scorecard/live-runs.json: pipeline.run "
                  "per seeded issue against a fresh git-initialized "
                  "copy of hackathon-demo-repo, ConnectorClient (Meta "
                  "Model API via custom.meta-model-api connector, no "
                  "env key). Split applied through ConnectorClient "
                  "role_models (the DAAS_MODEL_<ROLE> mechanism). "
                  "muse-wonder-1.0 availability probed live through "
                  "the connector before the runs (tiny JSON "
                  "completion, ok).",
        "split_config": {
            "CODER": SPLIT_ROLE_MODELS["CODER"],
            "REVIEWER": SPLIT_ROLE_MODELS["REVIEWER"],
            "TRIAGE": DEFAULT_MODEL + " (default)",
            "PLANNER": DEFAULT_MODEL + " (default)",
        },
        "uniform_baseline": {
            "source": "eval-scorecard/live-runs.json (Oct 25, 2026)",
            "config": "all roles muse-spark-1.3",
            "summary": baseline_summary,
        },
        "decision_rule_registered_before_runs": DECISION_RULE,
        "runs": runs,
        "summary": split_summary,
        "decision": decision,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    print(json.dumps({"split_summary": split_summary,
                      "decision": decision}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
