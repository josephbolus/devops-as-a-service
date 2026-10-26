#!/usr/bin/env python3
"""Spark-1.2 replicate eval: was iteration 28's +20 growth signal or variance?

Question (maximizer iteration 30): iteration 28 ran the full seeded
set LIVE with every role on muse-spark-1.2, once, and recorded an
unusually large total test growth of +20 (Tier 1 6 -> 13, Tier 2
6 -> 14, Tier 3 6 -> 11) in 88.59s — roughly double the +9/+10 growth
of the uniform, split, and spark-1.1 configurations. Iterations 28
and 29 both stated, in every artifact, that this single pass does
NOT re-decide the kept split and that its growth could be variance.

This runner is the replicate: the identical configuration (uniform
muse-spark-1.2 in all four roles, via the connector, fresh
git-initialized demo copies, one pass) run a second time, reported
honestly whatever the outcome. The record embeds the iteration-28
summary (read from eval-scorecard/model-fallback-runs.json at build
time) so the comparison is computed from both measured passes, not
asserted. This does NOT re-decide the kept split either: two passes
on n=3 seeded issues still cannot do that; it only tests whether
the +20 figure repeats.

Costs are character estimates (see daas/cost.py); spark-1.2 has no
published price in daas/cost.py, so its calls are priced at the
spark-1.3 rates by that module's documented unknown-model rule.
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
PRIOR_RECORD = ROOT / "eval-scorecard" / "model-fallback-runs.json"
ISSUES = [("tier1", "tier1.json"), ("tier2", "tier2.json"),
          ("tier3", "tier3.json"), ("guardrail", "guardrail.json")]
MODEL = "muse-spark-1.2"
CONFIG_LABEL = ("uniform muse-spark-1.2 in all four roles, via "
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


def _prior_summary():
    doc = json.loads(PRIOR_RECORD.read_text())
    runs = {r["slug"]: r for r in doc["runs"]}
    return {
        "source": "eval-scorecard/model-fallback-runs.json "
                  "(maximizer iteration 28)",
        "work_tiers_passed": doc["summary"]["work_tiers_passed"],
        "guardrail_escalated": doc["summary"]["guardrail_escalated"],
        "test_growth": doc["summary"]["test_growth"],
        "total_wall_clock_seconds": doc["summary"][
            "total_wall_clock_seconds"],
        "total_usd_est": doc["summary"]["total_usd_est"],
        "per_tier": {slug: [r["tests_before"], r["tests_after"]]
                     for slug, r in runs.items()},
    }


def build_record():
    runs = [run_one(slug, f) for slug, f in ISSUES]
    work = [r for r in runs if r["slug"] != "guardrail"]
    passed = [r for r in work if r["outcome"] == "passed"]
    growth = sum((r["tests_after"] - r["tests_before"]) for r in passed
                 if r["tests_after"] is not None)
    total_cost = round(sum((r["cost"] or {}).get("total_usd_est", 0.0)
                           for r in runs), 6)
    prior = _prior_summary()
    growths = [prior["test_growth"], growth]
    combined = {
        "passes": 2,
        "work_tiers_passed_each": [prior["work_tiers_passed"],
                                   f"{len(passed)}/{len(work)}"],
        "test_growth_each": growths,
        "test_growth_mean": round(sum(growths) / len(growths), 2),
        "test_growth_range": [min(growths), max(growths)],
        "both_guardrail_escalated": bool(
            prior["guardrail_escalated"] and any(
                r["outcome"] == "escalated" for r in runs
                if r["slug"] == "guardrail")),
    }
    return {
        "record": "Spark-1.2 replicate eval — second live pass of the "
                  "full seeded set with every role on muse-spark-1.2, "
                  "Oct 26, 2026 (maximizer iteration 30)",
        "method": "ConnectorClient only (Meta Model API via the "
                  "custom.meta-model-api connector, no env key). "
                  "pipeline.run per seeded issue against a fresh "
                  "git-initialized copy of hackathon-demo-repo, every "
                  "role on muse-spark-1.2 — the identical "
                  "configuration to iteration 28's fallback-config "
                  "runs. Prior-pass summary read from "
                  "eval-scorecard/model-fallback-runs.json. Costs are "
                  "character estimates; spark-1.2 calls are priced at "
                  "spark-1.3 rates under daas/cost.py's documented "
                  "unknown-model rule.",
        "config": CONFIG_LABEL,
        "runs": runs,
        "prior_pass": prior,
        "combined": combined,
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
    p = doc["prior_pass"]
    c = doc["combined"]
    lines = [
        "# Spark-1.2 replicate — was the +20 growth signal or variance? "
        "(Oct 26, 2026)",
        "",
        "Maximizer iteration 30. Iteration 28 ran the full seeded set "
        "live with every role on `muse-spark-1.2` once and recorded "
        "total test growth +20 — roughly double the +9/+10 growth of "
        "the uniform, split, and spark-1.1 configurations — and both "
        "iterations 28 and 29 stated that single pass does not "
        "re-decide the kept split. This file is the replicate: the "
        "identical configuration run a second time, reported as "
        "measured.",
        "",
        "## Replicate pass (iteration 30, all roles muse-spark-1.2)",
        "",
    ]
    for r in doc["runs"]:
        tb, ta = r["tests_before"], r["tests_after"]
        tests = f"{tb} → {ta}" if tb is not None else "n/a"
        cost = (f"${r['cost']['total_usd_est']:.4f}"
                if r.get("cost") else "n/a")
        lines.append(f"- {r['slug']}: **{r['outcome']}** — tests {tests}, "
                     f"{r['wall_clock_seconds']}s, est. cost {cost} "
                     "(char estimate, spark-1.2 priced at spark-1.3 "
                     "rates — see daas/cost.py unknown-model rule)")
    lines += [
        "",
        f"Replicate summary: work tiers passed {s['work_tiers_passed']}; "
        f"guardrail escalated: {s['guardrail_escalated']}; total test "
        f"growth +{s['test_growth']}; total wall clock "
        f"{s['total_wall_clock_seconds']}s; total est. cost "
        f"${s['total_usd_est']:.4f}.",
        "",
        "## Two-pass comparison (spark-1.2, all roles)",
        "",
        f"- Iteration 28 pass: work tiers {p['work_tiers_passed']}, "
        f"growth +{p['test_growth']}, {p['total_wall_clock_seconds']}s, "
        f"est. ${p['total_usd_est']:.4f} "
        f"(source: {p['source']})",
        f"- Iteration 30 replicate: work tiers {s['work_tiers_passed']}, "
        f"growth +{s['test_growth']}, {s['total_wall_clock_seconds']}s, "
        f"est. ${s['total_usd_est']:.4f}",
        f"- Combined: growth each {c['test_growth_each']}, mean "
        f"+{c['test_growth_mean']}, range "
        f"+{c['test_growth_range'][0]} to +{c['test_growth_range'][1]}; "
        f"guardrail escalated on both passes: "
        f"{c['both_guardrail_escalated']}.",
        "",
    ]
    # Verdict sentence is computed from the measured numbers, so the
    # markdown cannot claim a repeat the data does not show.
    if s["test_growth"] >= 18:
        verdict = ("The replicate growth is close to the original +20, "
                   "so the large growth on spark-1.2 repeated on a "
                   "second pass — it is not a one-pass fluke at this "
                   "sample size, though n=2 passes on n=3 seeded "
                   "issues still cannot re-decide the kept split.")
    elif s["test_growth"] >= 13:
        verdict = ("The replicate growth sits between the typical "
                   "+9/+10 of the other configurations and the "
                   "original +20, so the original figure is only "
                   "partly repeated: spark-1.2 may grow tests somewhat "
                   "more, but +20 itself looks like the high end of "
                   "variance at this sample size.")
    else:
        verdict = ("The replicate growth is in the same +9/+10 band as "
                   "the uniform, split, and spark-1.1 configurations, "
                   "so the original +20 does NOT repeat: at this "
                   "sample size it reads as variance, not a spark-1.2 "
                   "advantage.")
    lines += [
        f"Verdict (computed from the two measured growths): {verdict}",
        "",
        "Honest limits: this is the second pass of one alternate "
        "configuration on the seeded set (n=3 issues, now 2 attempts "
        "under spark-1.2). The kept live configuration remains the "
        "measured split (CODER/REVIEWER muse-wonder-1.0, "
        "TRIAGE/PLANNER muse-spark-1.3); neither pass re-decides it, "
        "and test growth is a secondary signal — pass counts tied at "
        "3/3 + guardrail in both spark-1.2 passes if the replicate "
        "also passed, which the rows above state as measured. No "
        "tool calling or responses-endpoint surface is claimed — "
        "the connector helper offers chat completions only. Costs "
        "are character estimates, not provider-reported usage.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "eval-scorecard"
                                         / "spark12-replicate-runs.json"))
    args = ap.parse_args()
    doc = build_record()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    (out.parent / "SPARK12_REPLICATE.md").write_text(render_md(doc))
    print(json.dumps({"summary": doc["summary"],
                      "combined": doc["combined"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
