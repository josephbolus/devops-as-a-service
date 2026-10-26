#!/usr/bin/env python3
"""Frontier replicate eval: does the contest configuration repeat?

Question (maximizer iteration 32): iteration 31 ran the full seeded
set LIVE with every role on muse-wonder-1.0 (the contest
configuration per Joseph's Oct 26 directive), once, and passed
3/3 + guardrail with growth +10 in 142.52s at est. $0.1124 -- and
its scorecard entry is capped verbatim at "one pass on the seeded
set". Every other multi-pass configuration in this repo earned its
repeatability claim from a replicate (split replicates, iterations
11/14; spark-1.2 replicate, iteration 30); the contest
configuration itself had none.

This runner is that replicate: the identical configuration (uniform
muse-wonder-1.0 in all four roles, muse-spark-1.3 configured only
as availability fallback, via the connector, fresh git-initialized
demo copies, one pass) run a second time, reported honestly
whatever the outcome. The record embeds the iteration-31 summary
(read from eval-scorecard/frontier-runs.json at build time) so the
comparison is computed from both measured passes, not asserted.

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
PRIOR_RECORD = ROOT / "eval-scorecard" / "frontier-runs.json"
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


def _prior_summary():
    doc = json.loads(PRIOR_RECORD.read_text())
    runs = {r["slug"]: r for r in doc["runs"]}
    return {
        "source": "eval-scorecard/frontier-runs.json "
                  "(maximizer iteration 31)",
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
    }


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
    prior = _prior_summary()
    growths = [prior["test_growth"], growth]
    walls = [prior["total_wall_clock_seconds"],
             round(sum(r["wall_clock_seconds"] for r in runs), 2)]
    costs = [prior["total_usd_est"], total_cost]
    combined = {
        "passes": 2,
        "work_tiers_passed_each": [prior["work_tiers_passed"],
                                   f"{len(passed)}/{len(work)}"],
        "test_growth_each": growths,
        "test_growth_mean": round(sum(growths) / len(growths), 2),
        "test_growth_range": [min(growths), max(growths)],
        "total_wall_clock_seconds_each": walls,
        "total_usd_est_each": costs,
        "cost_per_passed_issue_mean": round(
            sum(costs) / sum(int(p.split("/")[0]) for p in
                             [prior["work_tiers_passed"],
                              f"{len(passed)}/{len(work)}"]), 6)
        if passed else None,
        "both_guardrail_escalated": bool(
            prior["guardrail_escalated"] and any(
                r["outcome"] == "escalated" for r in runs
                if r["slug"] == "guardrail")),
        "both_passed_all_work_tiers": bool(
            prior["work_tiers_passed"] == "3/3"
            and f"{len(passed)}/{len(work)}" == "3/3"),
    }
    return {
        "record": "Frontier replicate eval -- second live pass of the "
                  "full seeded set with every role on muse-wonder-1.0 "
                  "(contest configuration), Oct 26, 2026 (maximizer "
                  "iteration 32)",
        "method": "ConnectorClient only (Meta Model API via the "
                  "custom.meta-model-api connector, no env key). "
                  "pipeline.run per seeded issue against a fresh "
                  "git-initialized copy of hackathon-demo-repo, every "
                  "role on muse-wonder-1.0; muse-spark-1.3 configured "
                  "only as availability fallback -- the identical "
                  "configuration to iteration 31's frontier runs. "
                  "Prior-pass summary read from "
                  "eval-scorecard/frontier-runs.json. Costs are "
                  "character estimates at wonder's published prices "
                  "($4/$20 per 1M in/out, daas/cost.py).",
        "config": CONFIG_LABEL,
        "model": MODEL,
        "fallback_model": FALLBACK,
        "per_role_models": per_role_models,
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
            "cost_per_passed_issue": round(total_cost / len(passed), 6)
            if passed else None,
        },
    }


def render_md(doc):
    s = doc["summary"]
    p = doc["prior_pass"]
    c = doc["combined"]
    lines = [
        "# Frontier replicate -- does the contest configuration repeat? "
        "(Oct 26, 2026)",
        "",
        "Maximizer iteration 32. Iteration 31 ran the full seeded set "
        "live with every role on `muse-wonder-1.0` (the contest "
        "configuration per Joseph's Oct 26 directive) once and passed "
        "3/3 + guardrail, growth +10, 142.52s, est. $0.1124 -- and was "
        "capped in the scorecard at one pass. This file is the "
        "replicate: the identical configuration run a second time, "
        "reported as measured.",
        "",
        "## Replicate pass (iteration 32, all roles muse-wonder-1.0)",
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
        f"Replicate summary: work tiers passed {s['work_tiers_passed']}; "
        f"guardrail escalated: {s['guardrail_escalated']}; total test "
        f"growth +{s['test_growth']}; total wall clock "
        f"{s['total_wall_clock_seconds']}s; total est. cost "
        f"${s['total_usd_est']:.4f}; est. cost per passed issue "
        f"${s['cost_per_passed_issue']:.4f}." if s["cost_per_passed_issue"] is not None else "",
        "",
        "## Two-pass comparison (all-frontier, muse-wonder-1.0)",
        "",
        f"- Iteration 31 pass: work tiers {p['work_tiers_passed']}, "
        f"growth +{p['test_growth']}, {p['total_wall_clock_seconds']}s, "
        f"est. ${p['total_usd_est']:.4f} "
        f"(source: {p['source']})",
        f"- Iteration 32 replicate: work tiers {s['work_tiers_passed']}, "
        f"growth +{s['test_growth']}, {s['total_wall_clock_seconds']}s, "
        f"est. ${s['total_usd_est']:.4f}",
        f"- Combined: both passes passed all work tiers: "
        f"{c['both_passed_all_work_tiers']}; growth each "
        f"{c['test_growth_each']}, mean +{c['test_growth_mean']}, range "
        f"+{c['test_growth_range'][0]} to +{c['test_growth_range'][1]}; "
        f"guardrail escalated on both passes: "
        f"{c['both_guardrail_escalated']}; two-pass mean est. cost per "
        f"passed issue ${c['cost_per_passed_issue_mean']:.4f}.",
        "",
    ]
    # Verdict is computed from the measured outcomes, so the markdown
    # cannot claim a repeat the data does not show.
    if c["both_passed_all_work_tiers"] and c["both_guardrail_escalated"]:
        verdict = ("The contest configuration repeated: both live "
                   "passes passed 3/3 work tiers with the guardrail "
                   "escalating, so the all-frontier record is no "
                   "longer a single pass. Growth and wall clock still "
                   "vary pass to pass (see the two-pass figures "
                   "above), and n=2 passes on n=3 seeded issues is "
                   "repeatability evidence, not a real-backlog claim.")
    else:
        verdict = ("The contest configuration did NOT fully repeat: "
                   "the replicate's measured outcomes above differ "
                   "from iteration 31's 3/3 + guardrail, and that "
                   "difference stands as recorded -- the all-frontier "
                   "record is two passes with the outcomes stated, "
                   "not a repeatability claim.")
    lines += [
        f"Verdict (computed from the two measured passes): {verdict}",
        "",
        "Honest limits: this is the second pass of the contest "
        "configuration on the seeded set (n=3 issues, now 2 attempts "
        "under all-frontier). Per-issue cost at wonder prices remains "
        "the highest of any configuration measured. No tool calling "
        "or responses-endpoint surface is claimed -- the connector "
        "helper offers chat completions only. Costs are character "
        "estimates, not provider-reported usage. Spark-tier models "
        "remain configured ONLY as availability fallbacks "
        "(`muse-spark-1.3` fallback; see fallback_stats in the JSON "
        "record).",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "eval-scorecard"
                                         / "frontier-replicate-runs.json"))
    args = ap.parse_args()
    doc = build_record()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    (out.parent / "FRONTIER_REPLICATE.md").write_text(render_md(doc))
    print(json.dumps({"summary": doc["summary"],
                      "combined": doc["combined"],
                      "per_role_models": doc["per_role_models"]},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
