#!/usr/bin/env python3
"""Frontier generalization (ledgerlite): contest config on unseen codebase #1.

Usage:
  python3 run_frontier_generalization_ledgerlite_eval.py [--out ../eval-scorecard/frontier-generalization-ledgerlite-runs.json]

Question (maximizer iteration 38, item-4 polish): iteration 33 measured
the all-frontier contest configuration on ONE unseen codebase
(gradebook). The other two unseen codebases (ledgerlite, textkit) still
only have split-config records. This runner measures the contest
configuration -- every role muse-wonder-1.0, muse-spark-1.3 only as
availability fallback -- on ledgerlite (generalization/, 9-test
baseline, median_cents even-count bug), the first unseen codebase.

Method: identical to run_generalization_eval.py / the iteration-33
frontier runner -- pipeline.run against a fresh git-initialized COPY
of ../generalization/ (vendored copy never run in place, not tuned),
ConnectorClient via the custom.meta-model-api connector (no env key),
plus an independent probe (written for this evaluation, NOT by the
pipeline) importing the fixed copy's ledgerlite package. The run only
counts as passed if the pipeline passes AND every probe check passes.
The iteration-15 split summary is read from
eval-scorecard/generalization-runs.json at build time.
"""
import argparse
import importlib
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
GEN_REPO = ROOT / "generalization"
ISSUE_FILE = GEN_REPO / "issue.json"
PRIOR_RECORD = ROOT / "eval-scorecard" / "generalization-runs.json"
MODEL = "muse-wonder-1.0"
FALLBACK = "muse-spark-1.3"
CONFIG_LABEL = ("all-frontier (contest config): every role "
                "muse-wonder-1.0, muse-spark-1.3 configured only as "
                "availability fallback")
PRODUCTION_FILES = ["ledgerlite/stats.py"]


class RecordingClient:
    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    def complete_json(self, system, user):
        role = system.strip().split()[0].upper()
        model = resolve_model(system, self.inner.model,
                              self.inner.role_models)
        self.calls.append({"role": role, "model": model})
        return self.inner.complete_json(system, user)


def run_probe(repo):
    for name in list(sys.modules):
        if name == "ledgerlite" or name.startswith("ledgerlite."):
            del sys.modules[name]
    sys.path.insert(0, str(repo))
    try:
        stats = importlib.import_module("ledgerlite.stats")
        cases = [
            ("median_cents([100, 200, 300, 400])", 250.0,
             stats.median_cents([100, 200, 300, 400])),
            ("median_cents([100, 200])", 150.0,
             stats.median_cents([100, 200])),
            ("median_cents([400, 100, 300, 200]) (unsorted)", 250.0,
             stats.median_cents([400, 100, 300, 200])),
            ("median_cents([10, 20, 30, 41])", 25.0,
             stats.median_cents([10, 20, 30, 41])),
            ("median_cents([100, 200, 300]) (odd, unchanged)", 200,
             stats.median_cents([100, 200, 300])),
            ("median_cents([42]) (single, unchanged)", 42,
             stats.median_cents([42])),
        ]
        return [{"check": n, "expected": e, "actual": a, "passed": a == e}
                for n, e, a in cases]
    finally:
        sys.path.remove(str(repo))


def _stats(client):
    inner = getattr(client, "inner", client)
    return (dict(getattr(inner, "fallback_stats",
                         {"fallbacks": 0, "fallback_successes": 0})),
            dict(getattr(inner, "retry_stats",
                         {"calls": 0, "retries": 0,
                          "transient_failures": 0})))


def run_one(client_factory):
    issue = json.loads(ISSUE_FILE.read_text())
    row = {"slug": "frontier-generalization-ledgerlite",
           "issue": issue["title"],
           "mode": "live-frontier-generalization",
           "config": CONFIG_LABEL,
           "target_codebase": "generalization/ (ledgerlite package)"}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        repo = tmp / "repo"
        shutil.copytree(GEN_REPO, repo,
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
            fb, rt = _stats(client)
            row.update({"outcome": "escalated",
                        "pipeline_outcome": "escalated",
                        "correct": False, "reason": e.reason,
                        "tests_before": None, "tests_after": None,
                        "files_touched": [], "unexpected_files": [],
                        "production_files_touched": [],
                        "wall_clock_seconds": wall,
                        "model_calls": len(client.calls),
                        "models_by_role": {},
                        "fallback_stats": fb, "retry_stats": rt,
                        "cost": getattr(e, "cost", None),
                        "pr_produced": False,
                        "probe": run_probe(repo), "probe_passed": False})
            return row, started
        except Exception as e:
            wall = round(time.perf_counter() - t0, 2)
            fb, rt = _stats(client)
            row.update({"outcome": "failed", "pipeline_outcome": "failed",
                        "correct": False,
                        "error": f"{type(e).__name__}: {e}"[:500],
                        "tests_before": None, "tests_after": None,
                        "files_touched": [], "unexpected_files": [],
                        "production_files_touched": [],
                        "wall_clock_seconds": wall,
                        "model_calls": len(client.calls),
                        "models_by_role": {c["role"]: c["model"]
                                           for c in client.calls},
                        "fallback_stats": fb, "retry_stats": rt,
                        "cost": None, "pr_produced": False,
                        "probe": run_probe(repo), "probe_passed": False})
            return row, started
        wall = round(time.perf_counter() - t0, 2)
        fb, rt = _stats(client)
        review = events.get("review", {})
        code = events.get("code", {})
        pr_body_path = tmp / "out" / "pr_body.md"
        probe = run_probe(repo)
        probe_passed = all(c["passed"] for c in probe)
        pipeline_passed = bool(result["passed"])
        touched = sorted(set(result["changed"]))
        outcome = ("passed" if pipeline_passed and probe_passed
                   else "partial" if pipeline_passed or probe_passed
                   else "failed")
        row.update({
            "outcome": outcome,
            "pipeline_outcome": "passed" if pipeline_passed else "failed",
            "correct": bool(pipeline_passed and probe_passed),
            "tests_before": result["tests_before"],
            "tests_after": result["tests_after"],
            "files_touched": touched,
            "production_files_touched": [f for f in touched
                                          if f in PRODUCTION_FILES],
            "unexpected_files": result["unexpected_files"],
            "wall_clock_seconds": wall,
            "model_calls": len(client.calls),
            "models_by_role": {c["role"]: c["model"]
                               for c in client.calls},
            "fallback_stats": fb, "retry_stats": rt,
            "tests_ok": result["tests_ok"],
            "reviewer_verdict": review.get("verdict"),
            "reviewer_notes": review.get("notes", ""),
            "pr_produced": bool(result["passed"]),
            "cost": result.get("cost"),
            "probe": probe,
            "probe_passed": probe_passed,
            "pr_body": pr_body_path.read_text()
            if pr_body_path.exists() else "",
            "diff": code.get("diff", ""),
        })
        return row, started


def _prior_summary():
    doc = json.loads(PRIOR_RECORD.read_text())
    r = doc["runs"][0]
    return {
        "source": "eval-scorecard/generalization-runs.json "
                  "(maximizer iteration 15, kept split config)",
        "config": doc["config"],
        "outcome": r["outcome"],
        "tests_before": r["tests_before"],
        "tests_after": r["tests_after"],
        "test_growth": doc["summary"]["test_growth"],
        "wall_clock_seconds": r["wall_clock_seconds"],
        "total_usd_est": (r.get("cost") or {}).get("total_usd_est"),
        "models_by_role": r["models_by_role"],
    }


def build_record():
    def factory():
        return RecordingClient(ConnectorClient(
            model=MODEL, role_models={}, fallback_model=FALLBACK))

    row, started = run_one(factory)
    row["started_at"] = started.isoformat()
    passed = row["outcome"] == "passed"
    return {
        "record": "Frontier generalization (ledgerlite) eval -- the "
                  "contest configuration (all roles muse-wonder-1.0) "
                  "run live on the unseen ledgerlite codebase, "
                  "Oct 26, 2026 (maximizer iteration 38)",
        "method": "pipeline.run (guardrail -> triage -> plan -> code "
                  "-> tests -> review) against a fresh git-initialized "
                  "copy of generalization/ (ledgerlite), "
                  "ConnectorClient (Meta Model API via the "
                  "custom.meta-model-api connector, no env key), "
                  "all-frontier contest config, plus an independent "
                  "probe of the median defect run against the fixed "
                  "copy afterwards. The vendored target was created "
                  "for iteration 15, was never run under the "
                  "all-frontier configuration before this run, and "
                  "was not tuned after the run. Prior split-config "
                  "summary read from "
                  "eval-scorecard/generalization-runs.json. Costs are "
                  "character estimates at wonder's published prices "
                  "($4/$20 per 1M in/out, daas/cost.py); the prior "
                  "split pass predates cost accounting, so it has no "
                  "recorded cost.",
        "config": CONFIG_LABEL,
        "model": MODEL,
        "fallback_model": FALLBACK,
        "target": {
            "codebase": "generalization/",
            "package": "ledgerlite",
            "baseline_tests": 9,
            "defects": [
                "ledgerlite/stats.py median_cents returns the upper "
                "middle value for even-length inputs instead of "
                "averaging the two middle values",
            ],
        },
        "runs": [row],
        "prior_split_pass": _prior_summary(),
        "summary": {
            "passed": passed,
            "outcome": row["outcome"],
            "pipeline_outcome": row["pipeline_outcome"],
            "probe_passed": row["probe_passed"],
            "tests_before": row.get("tests_before"),
            "tests_after": row.get("tests_after"),
            "test_growth": ((row["tests_after"] - row["tests_before"])
                            if row.get("tests_after") is not None
                            and row.get("tests_before") is not None
                            else None),
            "wall_clock_seconds": row["wall_clock_seconds"],
            "total_usd_est": (row.get("cost") or {}).get(
                "total_usd_est"),
            "files_touched": row.get("files_touched", []),
            "production_files_touched": row.get(
                "production_files_touched", []),
            "unexpected_files": row.get("unexpected_files", []),
        },
    }


def render_md(doc):
    s = doc["summary"]
    r = doc["runs"][0]
    p = doc["prior_split_pass"]
    cost = (f"${s['total_usd_est']:.4f}" if s["total_usd_est"] is not None
            else "n/a")
    probe_passed_count = sum(1 for c in r["probe"] if c["passed"])
    lines = [
        "# Frontier generalization (ledgerlite) -- the contest "
        "configuration on unseen codebase #1 (Oct 26, 2026)",
        "",
        "Maximizer iteration 38. Iteration 33 measured the "
        "all-frontier contest configuration (all four roles on "
        "`muse-wonder-1.0`, per Joseph's Oct 26 directive; "
        "`muse-spark-1.3` configured only as availability fallback) "
        "on one unseen codebase (gradebook). Ledgerlite -- the first "
        "unseen codebase (iteration 15) -- still only had a "
        "split-config record. This file is that missing measurement, "
        "reported as measured.",
        "",
        "## The target",
        "",
        "`generalization/` vendors **ledgerlite** (9-test baseline): "
        "`median_cents()` in `ledgerlite/stats.py` returns the upper "
        "middle value for even-length inputs instead of averaging "
        "the two middle values (baseline repro 300, expected 250). "
        "The vendored copy was not tuned after the run and still "
        "reproduces the bug in place; the pipeline ran against a "
        "fresh git-initialized copy.",
        "",
        "## Measured live run (connector, all-frontier contest config)",
        "",
        f"- Outcome: **{r['outcome']}** (pipeline: "
        f"{r['pipeline_outcome']}; independent probe: "
        f"{probe_passed_count}/{len(r['probe'])} checks passed)",
        (f"- Tests: {r['tests_before']} -> {r['tests_after']} "
         f"(growth +{s['test_growth']})" if s["test_growth"] is not None
         else "- Tests: n/a (run did not complete the tests stage)"),
        f"- Wall clock: {r['wall_clock_seconds']}s",
        f"- Model calls: {r['model_calls']}; models by role: "
        + ", ".join(f"{k}={v}" for k, v in
                    sorted(r["models_by_role"].items())),
        f"- Est. API cost: {cost} (char estimate at wonder prices "
        "$4/$20 per 1M)",
        f"- Reviewer: {r.get('reviewer_verdict')}",
        f"- Files touched: {', '.join(r['files_touched']) or 'none'}",
        f"- Production files touched: "
        f"{', '.join(r['production_files_touched']) or 'none'}",
        f"- Unexpected files: "
        f"{', '.join(r['unexpected_files']) or 'none'}",
        f"- Fallbacks: {r['fallback_stats']['fallbacks']} "
        f"(successes {r['fallback_stats']['fallback_successes']}); "
        f"retries: {r['retry_stats']['retries']}",
        "",
        "## Comparison with the same target under the split (iteration 15)",
        "",
        f"- Split pass (source: {p['source']}): outcome "
        f"{p['outcome']}, tests {p['tests_before']} -> "
        f"{p['tests_after']} (+{p['test_growth']}), "
        f"{p['wall_clock_seconds']}s, no recorded cost (the pass "
        "predates cost accounting).",
        f"- All-frontier pass (this run): outcome {r['outcome']}, "
        f"tests {r['tests_before']} -> {r['tests_after']}, "
        f"{r['wall_clock_seconds']}s, est. {cost}, probe passed: "
        f"{r['probe_passed']}.",
        "",
    ]
    if s["passed"]:
        verdict = ("The contest configuration generalized to a "
                   "second unseen codebase: frontier generalization "
                   "now rests on gradebook (multi-file, iteration 33) "
                   "and ledgerlite (this run), each probe-verified. "
                   "Textkit remains split-only. This is one run on a "
                   "small synthetic target already used for the split "
                   "record -- it does not add a new codebase or a "
                   "real-team claim.")
    else:
        verdict = ("The contest configuration did NOT fully pass on "
                   "this target as measured above; that outcome "
                   "stands as recorded.")
    lines += [
        f"Verdict (computed from the measured run): {verdict}",
        "",
        "Honest limits: one live run, on a small synthetic package "
        "written for this evaluation family (n=1 issue); no real "
        "users/backlog; review time remains the IMPACT_MODEL.md "
        "assumption. Costs are character estimates, not "
        "provider-reported usage.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(
        ROOT / "eval-scorecard"
        / "frontier-generalization-ledgerlite-runs.json"))
    args = ap.parse_args()
    doc = build_record()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    (out.parent / "FRONTIER_GENERALIZATION_LEDGERLITE.md").write_text(
        render_md(doc))
    print(json.dumps({"summary": doc["summary"],
                      "models_by_role": doc["runs"][0]["models_by_role"],
                      "fallback_stats": doc["runs"][0]["fallback_stats"],
                      "retry_stats": doc["runs"][0]["retry_stats"]},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
