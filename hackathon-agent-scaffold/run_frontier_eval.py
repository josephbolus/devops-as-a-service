#!/usr/bin/env python3
"""Frontier eval: contest configuration = ALL roles on the Meta frontier model.

Directive (Joseph, Oct 26, 2026, maximizer iteration 31): "Please use
meta frontier models for the contests." This supersedes the Oct 25
kept per-role split FOR CONTEST CONFIGURATION. The strongest model
verified through the connector is muse-wonder-1.0 (probed live this
iteration: muse-wonder-1.0 answered ok; muse-wonder-1.1 returned
HTTP 404 model_not_found, so no stronger frontier model is
available through the connector today).

This runner runs the full seeded set (Tier 1/2/3 + guardrail) LIVE
with EVERY role on muse-wonder-1.0 through the connector, one pass,
reported honestly whatever the outcomes. Spark-tier models are
configured ONLY as availability fallbacks (fallback_model=
muse-spark-1.3, used only on model-availability failure or
transient exhaustion per daas/llm.py; fallback_stats recorded).

Costs are character estimates at wonder's published prices in
daas/cost.py ($4/$20 per 1M in/out) -- real wonder pricing, unlike
the spark-1.1/1.2 runs which were priced at spark-1.3 rates.
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
MODEL = "muse-wonder-1.0"
FALLBACK = "muse-spark-1.3"
CONFIG_LABEL = ("all-frontier: uniform muse-wonder-1.0 in all four "
                "roles, via custom.meta-model-api connector, no env "
                "key; muse-spark-1.3 configured only as availability "
                "fallback")
# Prior configurations, from their written records (for comparison).
PRIOR = {
    "uniform_spark13": {"label": "Uniform muse-spark-1.3 (iteration 10)",
                        "test_growth": 9, "total_wall_clock_seconds": 94.65},
    "kept_split": {"label": "Kept split CODER/REVIEWER wonder-1.0, TRIAGE/PLANNER spark-1.3 (iterations 11/14)",
                   "test_growth": 10, "total_wall_clock_seconds": 209.14},
}


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
        client = ConnectorClient(model=MODEL, role_models={},
                                 fallback_model=FALLBACK)
        started = datetime.now(timezone.utc)
        t0 = time.monotonic()
        try:
            result = pipeline.run(repo, issue, client, tmp / "out")
        except pipeline.Escalation as e:
            row.update({"outcome": "escalated",
                        "correct": slug == "guardrail",
                        "wall_clock_seconds": round(time.monotonic() - t0, 2),
                        "tests_before": None, "tests_after": None,
                        "cost": e.cost,
                        "fallback_stats": dict(client.fallback_stats),
                        "retry_stats": dict(client.retry_stats)})
            row["started_at"] = started.isoformat()
            return row
        except Exception as e:
            row.update({"outcome": "failed", "correct": False,
                        "error": f"{type(e).__name__}: {e}"[:500],
                        "wall_clock_seconds": round(time.monotonic() - t0, 2),
                        "tests_before": None, "tests_after": None,
                        "cost": None,
                        "fallback_stats": dict(client.fallback_stats),
                        "retry_stats": dict(client.retry_stats)})
            row["started_at"] = started.isoformat()
            return row
        row.update({"outcome": "passed" if result["passed"] else "failed",
                    "correct": bool(result["passed"]),
                    "wall_clock_seconds": round(time.monotonic() - t0, 2),
                    "tests_before": result["tests_before"],
                    "tests_after": result["tests_after"],
                    "cost": result["cost"],
                    "fallback_stats": dict(client.fallback_stats),
                    "retry_stats": dict(client.retry_stats)})
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
    per_role_models = {}
    for r in runs:
        for role, blk in ((r.get("cost") or {}).get("per_role") or {}).items():
            per_role_models.setdefault(role, set()).update(blk.get("models", []))
    per_role_models = {k: sorted(v) for k, v in sorted(per_role_models.items())}
    return {
        "record": "Frontier eval -- full seeded set live with every role "
                  "on muse-wonder-1.0 (contest configuration per Joseph's "
                  "Oct 26 directive), Oct 26, 2026 (maximizer iteration 31)",
        "method": "ConnectorClient only (Meta Model API via the "
                  "custom.meta-model-api connector, no env key). "
                  "pipeline.run per seeded issue against a fresh "
                  "git-initialized copy of hackathon-demo-repo, every "
                  "role on muse-wonder-1.0; muse-spark-1.3 configured "
                  "only as availability fallback. Probe this iteration: "
                  "muse-wonder-1.0 answered ok through the connector; "
                  "muse-wonder-1.1 returned HTTP 404 model_not_found. "
                  "Costs are character estimates at wonder's published "
                  "prices ($4/$20 per 1M in/out, daas/cost.py).",
        "config": CONFIG_LABEL,
        "model": MODEL,
        "fallback_model": FALLBACK,
        "per_role_models": per_role_models,
        "prior_configs": PRIOR,
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
            "cost_per_passed_issue": round(total_cost / len(passed), 6) if passed else None,
        },
    }


def render_md(doc):
    s = doc["summary"]
    lines = [
        "# Frontier eval -- all roles on muse-wonder-1.0 (Oct 26, 2026)",
        "",
        "Maximizer iteration 31, per Joseph's Oct 26 directive: the "
        "contest configuration is ALL agent roles on the Meta frontier "
        "model. The strongest model verified through the connector is "
        "`muse-wonder-1.0` (probed live this iteration; "
        "`muse-wonder-1.1` returned HTTP 404 `model_not_found`). "
        "Spark-tier models remain configured ONLY as availability "
        "fallbacks (`muse-spark-1.3` fallback; see fallback_stats in "
        "the JSON record). This supersedes the Oct 25 kept per-role "
        "split for contest configuration; the split record stands as "
        "history.",
        "",
        "## Measured pass (all-frontier)",
        "",
    ]
    for r in doc["runs"]:
        tb, ta = r["tests_before"], r["tests_after"]
        tests = f"{tb} -> {ta}" if tb is not None else "n/a"
        cost = (f"${r['cost']['total_usd_est']:.4f}"
                if r.get("cost") else "n/a")
        lines.append(f"- {r['slug']}: **{r['outcome']}** -- tests {tests}, "
                     f"{r['wall_clock_seconds']}s, est. cost {cost} "
                     "(char estimate at wonder prices $4/$20 per 1M)")
    lines += [
        "",
        f"Summary: work tiers passed {s['work_tiers_passed']}; guardrail "
        f"escalated: {s['guardrail_escalated']}; total test growth "
        f"+{s['test_growth']}; total wall clock "
        f"{s['total_wall_clock_seconds']}s; total est. cost "
        f"${s['total_usd_est']:.4f}; est. cost per passed issue "
        f"${s['cost_per_passed_issue']:.4f}." if s["cost_per_passed_issue"] is not None else "",
        "",
        "## Comparison with prior configurations (their written records)",
        "",
        f"- Uniform muse-spark-1.3 (iteration 10): growth +9, 94.65s.",
        f"- Kept split (iterations 11/14): growth +10, 209.14s (split "
        "replicate 1; replicate 2 was +10 in 120.31s).",
        f"- All-frontier (this run): growth +{s['test_growth']}, "
        f"{s['total_wall_clock_seconds']}s, est. ${s['total_usd_est']:.4f}.",
        "",
        "Honest limits: one pass on the seeded set (n=3 issues). Wonder "
        "is the premium tier, so per-issue cost is expected to be the "
        "highest of any configuration measured; the figures above state "
        "it as measured. Costs are character estimates, not "
        "provider-reported usage. No tool calling or responses-endpoint "
        "surface is claimed.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "eval-scorecard" / "frontier-runs.json"))
    args = ap.parse_args()
    doc = build_record()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    (out.parent / "FRONTIER.md").write_text(render_md(doc))
    print(json.dumps({"summary": doc["summary"],
                      "per_role_models": doc["per_role_models"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
