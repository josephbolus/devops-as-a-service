#!/usr/bin/env python3
"""Expansion batch 3 eval: spec issues #5/#10/#11 run LIVE, all-frontier.

Joseph's Oct 26 issue-expansion directive (~7:05 AM MT): expand the
seeded set from 3 work issues toward 12 covering most DevOps/SRE
scenario families (spec: hackathon-issue-expansion-spec-2026-10-26.md).
Batch 3 seeds the final three families into hackathon-demo-repo as
genuine pre-existing defects, each with baseline tests that pass with
the bug present (the defect case is uncovered, like Tier 1):

  #5 retry storm            app/retryer.py  call_with_retry() never
                             sleeps, retrying in a tight loop
  #10 CI/CD expired token   app/deploy.py  run_deploy() crashes with
                             an unhandled error and logs the token
  #11 upstream pagination   app/apiclient.py  fetch_all() returns
                             only the first page, ignoring next_page

This runner runs each issue once LIVE through ConnectorClient under
the contest configuration (every role muse-wonder-1.0, spark-1.3 only
as availability fallback), against a fresh git-initialized copy of
the demo repo (baseline now 12 tests: 6 original + 6 expansion
baseline). Reported honestly whatever the outcomes; the vendored
demo repo is never run in place and was not tuned after seeding.
Costs are character estimates at wonder prices ($4/$20 per 1M).
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
ISSUES = [("retry-storm", "retry_storm.json", "#5 cascading failure / retry storm"),
          ("deploy-token", "deploy_token.json", "#10 CI/CD expired-token handling"),
          ("api-pagination", "api_pagination.json", "#11 upstream API pagination compatibility")]
MODEL = "muse-wonder-1.0"
FALLBACK = "muse-spark-1.3"
CONFIG_LABEL = ("all-frontier: uniform muse-wonder-1.0 in all four "
                "roles, via custom.meta-model-api connector, no env "
                "key; muse-spark-1.3 configured only as availability "
                "fallback")


def run_one(slug, issue_file, family):
    issue = json.loads((HERE / "issues" / issue_file).read_text())
    row = {"slug": slug, "family": family, "issue": issue["title"],
           "mode": "live", "config": CONFIG_LABEL}
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
            row.update({"outcome": "escalated", "correct": False,
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
    runs = [run_one(slug, f, fam) for slug, f, fam in ISSUES]
    passed = [r for r in runs if r["outcome"] == "passed"]
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
        "record": "Expansion batch 3 -- spec issues #5/#10/#11 live under "
                  "the all-frontier contest configuration, Oct 26, 2026 "
                  "(maximizer iteration 37, issue-expansion directive)",
        "method": "ConnectorClient only (Meta Model API via the "
                  "custom.meta-model-api connector, no env key). "
                  "pipeline.run per expansion issue against a fresh "
                  "git-initialized copy of hackathon-demo-repo (24-test "
                  "baseline: 6 original + 18 expansion baseline tests, "
                  "all passing with the seeded defects present). Costs "
                  "are character estimates at wonder's published prices "
                  "($4/$20 per 1M in/out, daas/cost.py).",
        "config": CONFIG_LABEL,
        "model": MODEL,
        "fallback_model": FALLBACK,
        "per_role_models": per_role_models,
        "runs": runs,
        "summary": {
            "issues_passed": f"{len(passed)}/{len(runs)}",
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
        "# Expansion batch 3 — issues #5/#10/#11 live, all-frontier (Oct 26, 2026)",
        "",
        "Issue-expansion directive (Joseph, Oct 26): the seeded set grows",
        "from 3 work issues toward 12 across researched DevOps/SRE families.",
        "Batch 3 seeds the final three families into the demo codebase",
        "as genuine pre-existing defects (baseline suite 24/24 passes",
        "present; the defect case is uncovered, exactly like Tier 1):",
        "",
        "- #5 cascading failure / retry storm — `app/retryer.py`:",
        "  `call_with_retry()` never sleeps between retries, so clients",
        "  hammer a struggling upstream in a tight loop.",
        "- #10 CI/CD + secrets — `app/deploy.py`: `run_deploy()` crashes",
        "  with an unhandled RuntimeError on an expired token and prints",
        "  the token itself in log lines and the error message.",
        "- #11 dependency/API compatibility — `app/apiclient.py`:",
        "  `fetch_all()` returns only the first page and ignores the",
        "  upstream's `next_page` cursor, silently truncating the list.",
        "",
        "## Measured pass (all-frontier contest configuration)",
        "",
    ]
    for r in doc["runs"]:
        tb, ta = r["tests_before"], r["tests_after"]
        tests = f"{tb} -> {ta}" if tb is not None else "n/a"
        cost = (f"${r['cost']['total_usd_est']:.4f}"
                if r.get("cost") else "n/a")
        line = (f"- {r['slug']} ({r['family']}): **{r['outcome']}** — "
                f"tests {tests}, {r['wall_clock_seconds']}s, est. cost "
                f"{cost} (char estimate at wonder prices $4/$20 per 1M)")
        if r.get("error"):
            line += f"; error: {r['error']}"
        lines.append(line)
    cpp = (f"${s['cost_per_passed_issue']:.4f}"
           if s["cost_per_passed_issue"] is not None else "n/a")
    lines += [
        "",
        f"Summary: issues passed {s['issues_passed']}; total test growth "
        f"+{s['test_growth']}; total wall clock "
        f"{s['total_wall_clock_seconds']}s; total est. cost "
        f"${s['total_usd_est']:.4f}; est. cost per passed issue {cpp}.",
        "",
        "Honest limits: one live pass per new issue (n=1 each) on the",
        "seeded demo codebase; no repeatability claim for the expanded",
        "set yet. With batch 3 the seeded work set reaches the spec's",
        "12 issues. Costs are character estimates, not provider-reported",
        "usage. The demo video still showcases the original three tiers;",
        "the expanded set is the evaluation bench behind it.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "eval-scorecard" / "expansion-batch3-runs.json"))
    args = ap.parse_args()
    doc = build_record()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    (out.parent / "EXPANSION_BATCH3.md").write_text(render_md(doc))
    print(json.dumps({"summary": doc["summary"],
                      "per_role_models": doc["per_role_models"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
