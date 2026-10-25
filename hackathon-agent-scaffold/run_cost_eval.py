#!/usr/bin/env python3
"""Per-run cost accounting eval: live runs with cost capture.

Usage:
  python3 run_cost_eval.py [--out ../eval-scorecard/cost-runs.json]

Question (maximizer new-feature backlog item 3, Oct 25): what does one
fixed issue actually cost in Meta Model API calls? Token usage is NOT
exposed on the connector path (the helper returns only the parsed
reply; see daas/cost.py), so the pipeline records per-role
character-count token ESTIMATES and prices them at the published
rates — labeled as estimates in every artifact that shows them.

Method: identical to the other live evals — pipeline.run per seeded
issue (Tier 1/2/3 + guardrail) against a fresh git-initialized copy
of the demo repo, ConnectorClient (no env key), kept split config
(CODER/REVIEWER=muse-wonder-1.0, TRIAGE/PLANNER=muse-spark-1.3).
Each row carries the pipeline's own cost summary plus the per-call
records from the run's cost.json. One pass over the set, reported
honestly whatever the outcomes.
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
from daas.llm import ConnectorClient  # noqa: E402

HERE = Path(__file__).parent
ROOT = HERE.parent
DEMO_REPO = ROOT / "hackathon-demo-repo"
SPLIT_ROLE_MODELS = {"CODER": "muse-wonder-1.0",
                     "REVIEWER": "muse-wonder-1.0"}
CONFIG_LABEL = ("split (kept config): CODER/REVIEWER=muse-wonder-1.0, "
                "TRIAGE/PLANNER=muse-spark-1.3")
ISSUES = [("tier1", "tier1.json"), ("tier2", "tier2.json"),
          ("tier3", "tier3.json"), ("guardrail", "guardrail.json")]


def run_one(slug, issue_file):
    issue = json.loads((HERE / "issues" / issue_file).read_text())
    row = {"slug": slug, "issue": issue["title"], "mode": "live",
           "config": CONFIG_LABEL}
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
        out = tmp / "out"
        client = ConnectorClient(role_models=dict(SPLIT_ROLE_MODELS))
        started = datetime.now(timezone.utc)
        t0 = time.monotonic()
        try:
            result = pipeline.run(repo, issue, client, out)
        except pipeline.Escalation as e:
            row.update({"outcome": "escalated",
                        "correct": slug == "guardrail",
                        "wall_clock_seconds": round(time.monotonic() - t0, 2),
                        "tests_before": None, "tests_after": None,
                        "cost": e.cost, "cost_calls": []})
            row["started_at"] = started.isoformat()
            return row
        cost_doc = json.loads((out / "cost.json").read_text())
        row.update({"outcome": "passed" if result["passed"] else "failed",
                    "correct": bool(result["passed"]),
                    "wall_clock_seconds": round(time.monotonic() - t0, 2),
                    "tests_before": result["tests_before"],
                    "tests_after": result["tests_after"],
                    "cost": result["cost"],
                    "cost_calls": cost_doc["calls"]})
        row["started_at"] = started.isoformat()
        return row


def build_record():
    runs = [run_one(slug, f) for slug, f in ISSUES]
    work = [r for r in runs if r["slug"] != "guardrail"]
    passed = [r for r in work if r["outcome"] == "passed"]
    per_role = {}
    for r in runs:
        for role, slot in (r["cost"] or {}).get("per_role", {}).items():
            agg = per_role.setdefault(role, {"calls": 0, "cost_usd_est": 0.0})
            agg["calls"] += slot["calls"]
            agg["cost_usd_est"] = round(agg["cost_usd_est"] + slot["cost_usd_est"], 6)
    total = round(sum(r["cost"]["total_usd_est"] for r in runs), 6)
    per_passed = (round(sum(r["cost"]["total_usd_est"] for r in passed)
                        / len(passed), 6) if passed else None)
    return {
        "record": "Per-run cost accounting — live runs with pipeline cost "
                  "capture, Oct 25, 2026 (maximizer backlog item 3)",
        "method": "pipeline.run per seeded issue against a fresh "
                  "git-initialized copy of hackathon-demo-repo, "
                  "ConnectorClient (Meta Model API via custom.meta-model-api "
                  "connector, no env key), kept split config. Token counts "
                  "are character-count ESTIMATES: the connector helper "
                  "returns only the parsed reply, so API usage never "
                  "reaches the pipeline (see daas/cost.py). Dollars are "
                  "estimates at published prices (spark $1.25/$4.25, "
                  "wonder $4/$20 per 1M tokens in/out).",
        "runs": runs,
        "summary": {
            "work_tiers_passed": f"{len(passed)}/{len(work)}",
            "guardrail_escalated": any(
                r["outcome"] == "escalated" for r in runs
                if r["slug"] == "guardrail"),
            "total_usd_est": total,
            "cost_per_passed_issue_usd_est": per_passed,
            "per_role_totals": per_role,
            "method": "char_estimate",
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out",
                    default=str(ROOT / "eval-scorecard" / "cost-runs.json"))
    args = ap.parse_args()
    record = build_record()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record["summary"], indent=2))
    return 0 if record["summary"]["work_tiers_passed"] == "3/3" else 1


if __name__ == "__main__":
    raise SystemExit(main())
