#!/usr/bin/env python3
"""Repeatability eval: re-run the live eval set under the kept split.

Usage:
  python3 run_repeatability_eval.py [--out ../eval-scorecard/repeat-runs.json]

Question (maximizer iteration 14, backlog-item-4 polish for Impact):
the Oct 25 live evidence was one run per tier per configuration —
uniform (live-runs.json) and split replicate 1 (split-runs.json).
Is the kept split configuration repeatable, or was replicate 1 luck?

Method: identical to the split experiment — pipeline.run per seeded
issue (Tier 1/2/3 + guardrail) against a fresh git-initialized copy of
hackathon-demo-repo, ConnectorClient (Meta Model API via the
custom.meta-model-api connector, no env key), kept split config
(CODER/REVIEWER=muse-wonder-1.0, TRIAGE/PLANNER=muse-spark-1.3,
via ConnectorClient role_models — the DAAS_MODEL_<ROLE> mechanism),
wall clock = pipeline duration, model actually used recorded per call.

This run is split replicate 2. The combined analysis in the output
folds in ALL timed live runs (uniform-1, split-1, split-2) using the
pure `aggregate()` function below, which the tests recompute from
the three committed records — no hand-entered totals.
"""
import argparse
import json
import shutil
import statistics
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
ISSUES = [("tier1", "tier1.json"), ("tier2", "tier2.json"),
          ("tier3", "tier3.json"), ("guardrail", "guardrail.json")]
SPLIT_ROLE_MODELS = {"CODER": "muse-wonder-1.0",
                     "REVIEWER": "muse-wonder-1.0"}
DEFAULT_MODEL = "muse-spark-1.3"
CONFIG_LABEL = "split (kept config): CODER/REVIEWER=muse-wonder-1.0, TRIAGE/PLANNER=muse-spark-1.3"


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


def _stats(values):
    if not values:
        return {"n": 0, "mean": None, "min": None, "max": None}
    return {"n": len(values),
            "mean": round(statistics.mean(values), 2),
            "min": min(values), "max": max(values)}


def aggregate(sources):
    """Combine timed live runs from named sources into per-tier stats.

    sources: list of (label, runs) where each run is a dict with
    slug/outcome/correct/wall_clock_seconds/tests_before/tests_after.
    Pure function — tests recompute the committed combined block
    from the three records with it.
    """
    per_slug = {}
    total_work = total_pass = 0
    guard_attempts = guard_correct = 0
    for label, runs in sources:
        for r in runs:
            slug = r["slug"]
            entry = per_slug.setdefault(slug, {
                "attempts": 0, "passes": 0, "sources": [],
                "wall_clock_seconds": [], "test_growth": []})
            entry["attempts"] += 1
            entry["sources"].append(label)
            entry["wall_clock_seconds"].append(r["wall_clock_seconds"])
            if slug == "guardrail":
                guard_attempts += 1
                if r.get("correct"):
                    guard_correct += 1
                    entry["passes"] += 1
            else:
                total_work += 1
                if r.get("outcome") == "passed" and r.get("correct"):
                    total_pass += 1
                    entry["passes"] += 1
                    entry["test_growth"].append(
                        r["tests_after"] - r["tests_before"])
    out_per = {}
    for slug, e in per_slug.items():
        out_per[slug] = {
            "attempts": e["attempts"], "passes": e["passes"],
            "pass_rate": f"{e['passes']}/{e['attempts']}",
            "sources": e["sources"],
            "wall_clock": _stats(e["wall_clock_seconds"]),
            "test_growth": _stats(e["test_growth"]),
        }
    return {
        "per_tier": out_per,
        "work_tiers": {"attempts": total_work, "passes": total_pass,
                       "pass_rate": f"{total_pass}/{total_work}"},
        "guardrail": {"attempts": guard_attempts, "correct": guard_correct,
                      "pass_rate": f"{guard_correct}/{guard_attempts}"},
    }


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


def _run_one(slug, issue_file, client_factory):
    issue = json.loads((HERE / "issues" / issue_file).read_text())
    row = {"slug": slug, "issue": issue["title"], "mode": "live-split-repeat"}
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
                            (tmp / "out" / "approval_request.json").exists()})
            return row, started
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
            return row, started
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
            "models_by_role": {c["role"]: c["model"] for c in client.calls},
            "tests_ok": result["tests_ok"],
            "reviewer_verdict": review.get("verdict"),
            "reviewer_notes": review.get("notes", ""),
            "pr_produced": bool(result["passed"]),
        })
        return row, started


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "eval-scorecard"
                                         / "repeat-runs.json"))
    args = ap.parse_args()

    def factory():
        return RecordingClient(ConnectorClient(
            model=DEFAULT_MODEL, role_models=dict(SPLIT_ROLE_MODELS)))

    runs = []
    for slug, f in ISSUES:
        row, started = _run_one(slug, f, factory)
        row["started_at"] = started.isoformat()
        runs.append(row)
        print(f"{slug}: {row['outcome']} wall={row['wall_clock_seconds']}s "
              f"tests={row.get('tests_before')}->{row.get('tests_after')}",
              flush=True)

    uniform = json.loads((ROOT / "eval-scorecard" / "live-runs.json").read_text())
    split1 = json.loads((ROOT / "eval-scorecard" / "split-runs.json").read_text())
    combined = aggregate([("uniform-1", uniform["runs"]),
                          ("split-1", split1["runs"]),
                          ("split-2", runs)])
    split_only = aggregate([("split-1", split1["runs"]), ("split-2", runs)])
    doc = {
        "record": "Repeatability eval — DevOps as a Service, Oct 25, 2026 "
                  "(maximizer iteration 14)",
        "method": "pipeline.run per seeded issue against a fresh "
                  "git-initialized copy of hackathon-demo-repo, "
                  "ConnectorClient (Meta Model API via custom.meta-model-api "
                  "connector, no env key), kept split config. This file is "
                  "split replicate 2; combined stats fold in uniform-1 "
                  "(live-runs.json) and split-1 (split-runs.json) via "
                  "run_repeatability_eval.aggregate().",
        "config": CONFIG_LABEL,
        "replicate": "split-2",
        "runs": runs,
        "summary": _summary(runs),
        "combined_all_live_timed": combined,
        "combined_split_only": split_only,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"summary: {doc['summary']}")
    print(f"combined work: {combined['work_tiers']} guardrail: {combined['guardrail']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
