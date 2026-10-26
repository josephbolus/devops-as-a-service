#!/usr/bin/env python3
"""Spark-1.1 replicate eval: does iteration 29's single pass repeat?

Question (maximizer iteration 43): iteration 29 ran the original
three work tiers + guardrail LIVE with every role on muse-spark-1.1,
once, and passed 3/3 + guardrail (growth +10, 77.67s). Since then
spark-1.1 was the last model in the Tooling record with only a
single pipeline pass: spark-1.2 was replicated at iteration 30 and
the all-frontier contest configuration at iteration 32.

This runner is the replicate: the identical model configuration
(uniform muse-spark-1.1 in all four roles, via the connector, fresh
git-initialized demo copies, one pass over the original three work
tiers + guardrail), reported honestly whatever the outcome.

BASELINE CAVEAT, stated up front: iteration 29 ran at the
pre-expansion 6-test demo baseline; iterations 35-37 expanded the
demo repo to 24 tests, so this replicate's tests_before is 24, not
6. Pass/fail and test-growth deltas are comparable across the two
passes; absolute test counts are not, and no artifact claims they
are. The record embeds the iteration-29 summary (read from
eval-scorecard/spark11-runs.json at build time) so the comparison
is computed from both measured passes, not asserted.

This does NOT re-decide the contest configuration: since iteration
31 the contest configuration is all-frontier (every role
muse-wonder-1.0, spark only as availability fallback). Spark-1.1 is
a non-contest, fallback-tier model; this replicate only removes its
single-pass status in the Tooling record.

Costs are character estimates (see daas/cost.py); spark-1.1 has no
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
PRIOR_RECORD = ROOT / "eval-scorecard" / "spark11-runs.json"
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


def _prior_summary():
    doc = json.loads(PRIOR_RECORD.read_text())
    runs = {r["slug"]: r for r in doc["runs"]}
    return {
        "source": "eval-scorecard/spark11-runs.json "
                  "(maximizer iteration 29)",
        "work_tiers_passed": doc["summary"]["work_tiers_passed"],
        "guardrail_escalated": doc["summary"]["guardrail_escalated"],
        "test_growth": doc["summary"]["test_growth"],
        "total_wall_clock_seconds": doc["summary"][
            "total_wall_clock_seconds"],
        "total_usd_est": doc["summary"]["total_usd_est"],
        "demo_baseline_tests": runs["tier1"]["tests_before"],
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
        "baseline_changed_between_passes": True,
        "demo_baseline_tests_each": [
            prior["demo_baseline_tests"],
            next((r["tests_before"] for r in work
                  if r["tests_before"] is not None), None)],
    }
    return {
        "record": "Spark-1.1 replicate eval — second live pass of the "
                  "original seeded tiers with every role on "
                  "muse-spark-1.1, Oct 26, 2026 (maximizer "
                  "iteration 43)",
        "method": "ConnectorClient only (Meta Model API via the "
                  "custom.meta-model-api connector, no env key). "
                  "pipeline.run per seeded issue against a fresh "
                  "git-initialized copy of hackathon-demo-repo, every "
                  "role on muse-spark-1.1 — the identical model "
                  "configuration to iteration 29. Prior-pass summary "
                  "read from eval-scorecard/spark11-runs.json. The "
                  "demo baseline grew from 6 to 24 tests between the "
                  "passes (iterations 35-37), so absolute counts "
                  "differ; pass/fail and growth deltas are the "
                  "comparable quantities. Costs are character "
                  "estimates; spark-1.1 calls are priced at spark-1.3 "
                  "rates under daas/cost.py's documented "
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
        "# Spark-1.1 replicate — does iteration 29's pass repeat? "
        "(Oct 26, 2026)",
        "",
        "Maximizer iteration 43. Iteration 29 ran the original three "
        "work tiers live with every role on `muse-spark-1.1` once "
        "and passed 3/3 + guardrail (growth +10, 77.67s). It was "
        "since then the last model in the Tooling record with only "
        "a single pipeline pass — spark-1.2 was replicated at "
        "iteration 30 and the all-frontier contest configuration at "
        "iteration 32. This file is the replicate: the identical "
        "model configuration run a second time, reported as "
        "measured, NOT re-run for a cleaner record.",
        "",
        "Baseline caveat: iteration 29 ran at the pre-expansion "
        "6-test demo baseline; this replicate runs at the current "
        "24-test baseline (iterations 35–37), so tests_before is 24 "
        "below, not 6. Pass/fail and growth deltas are comparable "
        "across the passes; absolute test counts are not.",
        "",
        "## Replicate pass (iteration 43, all roles muse-spark-1.1)",
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
        f"Replicate summary: work tiers passed {s['work_tiers_passed']}; "
        f"guardrail escalated: {s['guardrail_escalated']}; total test "
        f"growth +{s['test_growth']}; total wall clock "
        f"{s['total_wall_clock_seconds']}s; total est. cost "
        f"${s['total_usd_est']:.4f}.",
        "",
        "## Two-pass comparison (spark-1.1, all roles)",
        "",
        f"- Iteration 29 pass: work tiers {p['work_tiers_passed']}, "
        f"growth +{p['test_growth']}, {p['total_wall_clock_seconds']}s, "
        f"est. ${p['total_usd_est']:.4f}, at the "
        f"{p['demo_baseline_tests']}-test demo baseline "
        f"(source: {p['source']})",
        f"- Iteration 43 replicate: work tiers {s['work_tiers_passed']}, "
        f"growth +{s['test_growth']}, {s['total_wall_clock_seconds']}s, "
        f"est. ${s['total_usd_est']:.4f}, at the "
        f"{c['demo_baseline_tests_each'][1]}-test demo baseline",
        f"- Combined: growth each {c['test_growth_each']}, mean "
        f"+{c['test_growth_mean']}, range "
        f"+{c['test_growth_range'][0]} to +{c['test_growth_range'][1]}; "
        f"guardrail escalated on both passes: "
        f"{c['both_guardrail_escalated']}.",
        "",
    ]
    # Verdict sentence is computed from the measured outcomes, so the
    # markdown cannot claim a repeat the data does not show.
    if s["work_tiers_passed"] == p["work_tiers_passed"] == "3/3" \
            and s["guardrail_escalated"]:
        verdict = ("The replicate repeats iteration 29's outcome "
                   "exactly at the outcome level — 3/3 work tiers "
                   "passed and the guardrail escalated — so "
                   "spark-1.1's single-pass status is removed: every "
                   "probed Meta model now has at least two live "
                   "pipeline passes. Growth deltas across the two "
                   "passes are stated above as measured; the "
                   "baseline change (6 → 24 tests) means the "
                   "absolute counts are not compared.")
    else:
        verdict = ("The replicate did NOT repeat iteration 29's "
                   "outcome exactly — the rows above state what "
                   "actually happened, and that measured shortfall "
                   "stands as the record: spark-1.1's two-pass "
                   "record is one full pass (iteration 29) plus this "
                   "replicate as measured, with no re-run taken for "
                   "a cleaner result.")
    lines += [
        f"Verdict (computed from the two measured passes): {verdict}",
        "",
        "Honest limits: this is the second pass of one non-contest "
        "configuration on the original three seeded tiers (n=3 "
        "issues). The contest configuration remains all-frontier "
        "(every role muse-wonder-1.0, spark only as availability "
        "fallback, per Joseph's Oct 26 directive); neither spark-1.1 "
        "pass re-decides it. No tool calling or responses-endpoint "
        "surface is claimed — the connector helper offers chat "
        "completions only. Costs are character estimates, not "
        "provider-reported usage.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "eval-scorecard"
                                         / "spark11-replicate-runs.json"))
    args = ap.parse_args()
    doc = build_record()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    (out.parent / "SPARK11_REPLICATE.md").write_text(render_md(doc))
    print(json.dumps({"summary": doc["summary"],
                      "combined": doc["combined"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
