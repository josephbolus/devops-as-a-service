#!/usr/bin/env python3
"""Spark-1.1 pipeline eval: the last probe-only model, run live end to end.

Question (maximizer iteration 29): the Tooling record's remaining
model cap after iteration 28 was that `muse-spark-1.1` was
probe-proven only — a tiny completion, never a pipeline run. This
runner runs the full seeded set (Tier 1/2/3 + guardrail) LIVE with
EVERY role on muse-spark-1.1 through the connector, one pass,
reported honestly whatever the outcomes.

Costs are character estimates (see daas/cost.py); spark-1.1 has no
published price in daas/cost.py, so its calls are priced at the
spark-1.3 rates by that module's documented unknown-model rule —
an estimate assumption, stated wherever the number appears.
This does NOT re-decide the kept split configuration.
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
ISSUES = [("tier1", "tier1.json"), ("tier2", "tier2.json"),
          ("tier3", "tier3.json"), ("guardrail", "guardrail.json")]
MODEL = "muse-spark-1.1"
CONFIG_LABEL = ("uniform muse-spark-1.1 in all four roles, via "
                "custom.meta-model-api connector, no env key")


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
        client = ConnectorClient(model=MODEL, role_models={})
        started = datetime.now(timezone.utc)
        t0 = time.monotonic()
        try:
            result = pipeline.run(repo, issue, client, tmp / "out")
        except pipeline.Escalation as e:
            row.update({"outcome": "escalated",
                        "correct": slug == "guardrail",
                        "wall_clock_seconds": round(
                            time.monotonic() - t0, 2),
                        "tests_before": None, "tests_after": None,
                        "cost": e.cost,
                        "fallback_stats": dict(client.fallback_stats)})
            row["started_at"] = started.isoformat()
            return row
        except Exception as e:  # a failed live run is a measured result
            row.update({"outcome": "failed", "correct": False,
                        "error": f"{type(e).__name__}: {e}"[:500],
                        "wall_clock_seconds": round(
                            time.monotonic() - t0, 2),
                        "tests_before": None, "tests_after": None,
                        "cost": None,
                        "fallback_stats": dict(client.fallback_stats)})
            row["started_at"] = started.isoformat()
            return row
        row.update({"outcome": "passed" if result["passed"] else "failed",
                    "correct": bool(result["passed"]),
                    "wall_clock_seconds": round(time.monotonic() - t0, 2),
                    "tests_before": result["tests_before"],
                    "tests_after": result["tests_after"],
                    "cost": result["cost"],
                    "fallback_stats": dict(client.fallback_stats)})
        row["started_at"] = started.isoformat()
        return row


def build_record():
    runs = [run_one(slug, f) for slug, f in ISSUES]
    work = [r for r in runs if r["slug"] != "guardrail"]
    passed = [r for r in work if r["outcome"] == "passed"]
    growth = sum((r["tests_after"] - r["tests_before"]) for r in passed
                 if r["tests_after"] is not None)
    total_cost = round(sum((r["cost"] or {}).get("total_usd_est", 0.0)
                           for r in runs), 6)
    return {
        "record": "Spark-1.1 pipeline eval — the full seeded set live "
                  "with every role on muse-spark-1.1, Oct 26, 2026 "
                  "(maximizer iteration 29)",
        "method": "ConnectorClient only (Meta Model API via the "
                  "custom.meta-model-api connector, no env key). "
                  "pipeline.run per seeded issue against a fresh "
                  "git-initialized copy of hackathon-demo-repo, every "
                  "role on muse-spark-1.1. Costs are character "
                  "estimates; spark-1.1 calls are priced at spark-1.3 "
                  "rates under daas/cost.py's documented "
                  "unknown-model rule.",
        "config": CONFIG_LABEL,
        "runs": runs,
        "summary": {
            "work_tiers_passed": f"{len(passed)}/{len(work)}",
            "guardrail_escalated": any(
                r["outcome"] == "escalated" for r in runs
                if r["slug"] == "guardrail"),
            "test_growth": growth,
            "total_wall_clock_seconds": round(
                sum(r["wall_clock_seconds"] for r in runs), 2),
            "total_usd_est": total_cost,
        },
    }


def render_md(doc):
    s = doc["summary"]
    lines = [
        "# Spark-1.1 — live pipeline validation (Oct 26, 2026)",
        "",
        "Maximizer iteration 29. Until this iteration `muse-spark-1.1` "
        "was the one probed Meta model with no pipeline run: iteration "
        "28 proved it only with a tiny completion. This file is the "
        "live record of the full seeded set with every role on "
        "muse-spark-1.1, through the connector.",
        "",
        "## Full seeded set on muse-spark-1.1 (all roles)",
        "",
    ]
    for r in doc["runs"]:
        tb, ta = r["tests_before"], r["tests_after"]
        tests = f"{tb} → {ta}" if tb is not None else "n/a"
        cost = (f"${r['cost']['total_usd_est']:.4f}"
                if r.get("cost") else "n/a")
        lines.append(f"- {r['slug']}: **{r['outcome']}** — tests {tests}, "
                     f"{r['wall_clock_seconds']}s, est. cost {cost} "
                     "(char estimate, spark-1.1 priced at spark-1.3 "
                     "rates — see daas/cost.py unknown-model rule)")
    lines += [
        "",
        f"Summary: work tiers passed {s['work_tiers_passed']}; "
        f"guardrail escalated: {s['guardrail_escalated']}; total test "
        f"growth +{s['test_growth']}; total wall clock "
        f"{s['total_wall_clock_seconds']}s; total est. cost "
        f"${s['total_usd_est']:.4f}.",
        "",
        "Honest limits: this is one pass on the seeded set. Each of "
        "the three spark models (1.3, 1.2, 1.1) has now served all "
        "four production roles live — spark-1.3 in the kept split and "
        "the uniform baseline, spark-1.2 in iteration 28, spark-1.1 "
        "here. Wonder-1.0 remains proven only in the CODER and "
        "REVIEWER roles and is not claimed in TRIAGE or PLANNER. "
        "The kept live configuration "
        "remains the measured split (CODER/REVIEWER muse-wonder-1.0, "
        "TRIAGE/PLANNER muse-spark-1.3); this iteration proves a "
        "fourth model in production roles, it does not re-decide the "
        "split. No tool calling or responses-endpoint surface is "
        "claimed — the connector helper offers chat completions only.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "eval-scorecard"
                                         / "spark11-runs.json"))
    args = ap.parse_args()
    doc = build_record()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    (out.parent / "SPARK11.md").write_text(render_md(doc))
    print(json.dumps(doc["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
