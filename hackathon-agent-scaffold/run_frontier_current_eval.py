#!/usr/bin/env python3
"""Frontier current-baseline eval: the original tiers, direct, at 24.

Question (maximizer iteration 48): the all-frontier contest
configuration's DIRECT-pipeline record for the original seeded set
(iterations 31/32: two passes, 3/3 + guardrail each, growth +10/+9)
was measured at the pre-expansion 6-test demo baseline. Since then
the demo repo tripled to 24 tests (iterations 35-37 expansion
seeding), and every other measured shape has been re-proven at the
current baseline -- the expansion set (iteration 44, direct), the
Judge Mode tours (iterations 40/41, console), spark-1.1 (iteration
43), the human gate (iteration 47). The original tiers' direct
record under the contest configuration was the one stale-baseline
remainder.

This runner closes that gap: Tier 1/2/3 + guardrail, once each,
LIVE through ConnectorClient under the identical contest
configuration (every role muse-wonder-1.0, spark-1.3 only as
availability fallback), against fresh git-initialized copies of
the demo repo at the current 24-test baseline, reported honestly
whatever the outcome and NOT re-run for a cleaner record. The
record embeds both prior frontier passes (read from
frontier-runs.json and frontier-replicate-runs.json at build
time) so the three-pass comparison computes from measured
passes, not asserted. Growth deltas are the comparable quantity
across the baseline change; absolute counts carry that caveat.

Costs are character estimates at wonder's published prices in
daas/cost.py ($4/$20 per 1M in/out).
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
PRIOR_FILES = [("iteration 31", "frontier-runs.json"),
               ("iteration 32", "frontier-replicate-runs.json")]
ISSUES = [("tier1", "tier1.json"), ("tier2", "tier2.json"),
          ("tier3", "tier3.json"), ("guardrail", "guardrail.json")]
MODEL = "muse-wonder-1.0"
FALLBACK = "muse-spark-1.3"
CONFIG_LABEL = ("all-frontier: uniform muse-wonder-1.0 in all four "
                "roles, via custom.meta-model-api connector, no env "
                "key; muse-spark-1.3 configured only as availability "
                "fallback")


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
                        "wall_clock_seconds": round(
                            time.monotonic() - t0, 2),
                        "tests_before": None, "tests_after": None,
                        "cost": e.cost,
                        "fallback_stats": dict(client.fallback_stats),
                        "retry_stats": dict(client.retry_stats)})
            row["started_at"] = started.isoformat()
            return row
        except Exception as e:  # a failed live run is a measured result
            row.update({"outcome": "failed", "correct": False,
                        "error": f"{type(e).__name__}: {e}"[:500],
                        "wall_clock_seconds": round(
                            time.monotonic() - t0, 2),
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


def _prior_passes():
    out = []
    for label, name in PRIOR_FILES:
        doc = json.loads((ROOT / "eval-scorecard" / name).read_text())
        runs = {r["slug"]: r for r in doc["runs"]}
        out.append({
            "label": label,
            "source": f"eval-scorecard/{name}",
            "work_tiers_passed": doc["summary"]["work_tiers_passed"],
            "guardrail_escalated": doc["summary"]["guardrail_escalated"],
            "test_growth": doc["summary"]["test_growth"],
            "total_wall_clock_seconds": doc["summary"][
                "total_wall_clock_seconds"],
            "total_usd_est": doc["summary"]["total_usd_est"],
            "cost_per_passed_issue": doc["summary"][
                "cost_per_passed_issue"],
            "per_tier": {slug: [r["tests_before"], r["tests_after"]]
                         for slug, r in runs.items()},
        })
    return out


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
            per_role_models.setdefault(role, set()).update(
                blk.get("models", []))
    per_role_models = {k: sorted(v)
                       for k, v in sorted(per_role_models.items())}
    priors = _prior_passes()
    this_passed = f"{len(passed)}/{len(work)}"
    this_guardrail = any(r["outcome"] == "escalated" for r in runs
                         if r["slug"] == "guardrail")
    growths = [p["test_growth"] for p in priors] + [growth]
    passed_each = [p["work_tiers_passed"] for p in priors] + [this_passed]
    combined = {
        "passes": len(priors) + 1,
        "work_tiers_passed_each": passed_each,
        "test_growth_each": growths,
        "test_growth_mean": round(sum(growths) / len(growths), 2),
        "test_growth_range": [min(growths), max(growths)],
        "all_passes_passed_all_work_tiers": all(
            p == "3/3" for p in passed_each),
        "all_passes_guardrail_escalated": bool(
            all(p["guardrail_escalated"] for p in priors) and this_guardrail),
        "per_tier_growth_each": {
            r["slug"]: [
                (p["per_tier"][r["slug"]][1] - p["per_tier"][r["slug"]][0])
                if p["per_tier"].get(r["slug"]) and
                p["per_tier"][r["slug"]][0] is not None else None
                for p in priors] + [
                (r["tests_after"] - r["tests_before"])
                if r["tests_after"] is not None else None]
            for r in work},
    }
    return {
        "record": "Frontier current-baseline eval -- direct-pipeline "
                  "live pass of the original seeded set (Tier 1/2/3 + "
                  "guardrail) under the all-frontier contest "
                  "configuration at the current 24-test demo baseline, "
                  "Oct 26, 2026 (maximizer iteration 48)",
        "method": "ConnectorClient only (Meta Model API via the "
                  "custom.meta-model-api connector, no env key). "
                  "pipeline.run per seeded issue against a fresh "
                  "git-initialized copy of hackathon-demo-repo "
                  "(24-test baseline), every role on muse-wonder-1.0; "
                  "muse-spark-1.3 configured only as availability "
                  "fallback -- the identical contest configuration to "
                  "iterations 31/32, whose passes ran at the "
                  "pre-expansion 6-test baseline. Prior-pass summaries "
                  "read from eval-scorecard/frontier-runs.json and "
                  "frontier-replicate-runs.json. Costs are character "
                  "estimates at wonder's published prices ($4/$20 per "
                  "1M in/out, daas/cost.py).",
        "config": CONFIG_LABEL,
        "model": MODEL,
        "fallback_model": FALLBACK,
        "per_role_models": per_role_models,
        "runs": runs,
        "prior_passes": priors,
        "combined": combined,
        "summary": {
            "work_tiers_passed": this_passed,
            "guardrail_escalated": this_guardrail,
            "test_growth": growth,
            "total_wall_clock_seconds": round(
                sum(r["wall_clock_seconds"] for r in runs), 2),
            "total_usd_est": total_cost,
            "cost_per_passed_issue": round(total_cost / len(passed), 6)
            if passed else None,
        },
    }


def render_md(doc):
    s = doc["summary"]
    c = doc["combined"]
    lines = [
        "# Frontier current-baseline -- original tiers, direct pipeline, at 24 tests (Oct 26, 2026)",
        "",
        "Maximizer iteration 48. The all-frontier contest",
        "configuration's direct-pipeline record for the original",
        "seeded set (iterations 31/32: two passes, 3/3 + guardrail",
        "each, growth +10/+9) was measured at the pre-expansion",
        "6-test demo baseline. The demo repo has since tripled to",
        "24 tests (expansion seeding, iterations 35-37), and every",
        "other measured shape has been re-proven at the current",
        "baseline (expansion direct replicate iteration 44, Judge",
        "Mode tours iterations 40/41, spark-1.1 iteration 43,",
        "human gate iteration 47). This file is the original tiers'",
        "direct-pipeline pass at the current baseline: Tier 1/2/3 +",
        "guardrail run once each under the identical contest",
        "configuration, reported as measured and NOT re-run for a",
        "cleaner record. Growth deltas are the quantity comparable",
        "across the baseline change; absolute counts carry that",
        "caveat.",
        "",
        "## Current-baseline pass (iteration 48, all roles muse-wonder-1.0)",
        "",
    ]
    for r in doc["runs"]:
        tb, ta = r["tests_before"], r["tests_after"]
        tests = f"{tb} -> {ta}" if tb is not None else "n/a"
        cost = (f"${r['cost']['total_usd_est']:.4f}"
                if r.get("cost") else "n/a")
        line = (f"- {r['slug']}: **{r['outcome']}** -- tests {tests}, "
                f"{r['wall_clock_seconds']}s, est. cost {cost} "
                "(char estimate at wonder prices $4/$20 per 1M)")
        if r.get("error"):
            line += f"; error: {r['error']}"
        lines.append(line)
    cpp = (f"${s['cost_per_passed_issue']:.4f}"
           if s["cost_per_passed_issue"] is not None else "n/a")
    lines += [
        "",
        f"Pass summary: work tiers passed {s['work_tiers_passed']}; "
        f"guardrail escalated: {s['guardrail_escalated']}; total test "
        f"growth +{s['test_growth']}; total wall clock "
        f"{s['total_wall_clock_seconds']}s; total est. cost "
        f"${s['total_usd_est']:.4f}; est. cost per passed issue {cpp}.",
        "",
        "## Three-pass comparison (all-frontier, direct pipeline)",
        "",
    ]
    for p in doc["prior_passes"]:
        lines.append(
            f"- {p['label']} pass (6-test baseline): work tiers "
            f"{p['work_tiers_passed']}, growth +{p['test_growth']}, "
            f"{p['total_wall_clock_seconds']}s, est. "
            f"${p['total_usd_est']:.4f} (source: {p['source']})")
    lines += [
        f"- Iteration 48 pass (24-test baseline): work tiers "
        f"{s['work_tiers_passed']}, growth +{s['test_growth']}, "
        f"{s['total_wall_clock_seconds']}s, est. "
        f"${s['total_usd_est']:.4f}",
        f"- Combined: work tiers each "
        f"{c['work_tiers_passed_each']}; growth each "
        f"{c['test_growth_each']}, mean +{c['test_growth_mean']}, "
        f"range +{c['test_growth_range'][0]} to "
        f"+{c['test_growth_range'][1]}; guardrail escalated on all "
        f"passes: {c['all_passes_guardrail_escalated']}.",
        "",
    ]
    if (c["all_passes_passed_all_work_tiers"]
            and c["all_passes_guardrail_escalated"]):
        verdict = ("The contest configuration's direct record now "
                   "holds at the baseline judges will actually see: "
                   "three direct passes, 3/3 work tiers and a "
                   "guardrail escalation on each, the third at the "
                   "current 24-test baseline -- the original tiers' "
                   "direct record is no longer stale-baseline. Growth "
                   "still varies pass to pass (see above).")
    else:
        verdict = ("The current-baseline pass did NOT match the "
                   "prior passes' 3/3 + guardrail outcome -- the rows "
                   "above state what actually happened, and that "
                   "measured result stands as the record, with no "
                   "re-run taken for a cleaner result.")
    lines += [
        f"Verdict (computed from the three measured passes): {verdict}",
        "",
        "Honest limits: three direct passes of the original tiers",
        "on the seeded demo codebase (the first two at the 6-test",
        "baseline, this one at 24); no real users or real backlog,",
        "and review time is still the impact model's 10-minute",
        "assumption. This pass goes through pipeline.run directly,",
        "not the demo console (the console path at this baseline",
        "is iteration 40's record). Costs are character estimates,",
        "not provider-reported usage.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "eval-scorecard"
                                         / "frontier-current-runs.json"))
    args = ap.parse_args()
    doc = build_record()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    (out.parent / "FRONTIER_CURRENT.md").write_text(render_md(doc))
    print(json.dumps({"summary": doc["summary"],
                      "combined": doc["combined"],
                      "per_role_models": doc["per_role_models"]},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
