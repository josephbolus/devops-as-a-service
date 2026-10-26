#!/usr/bin/env python3
"""Frontier generalization eval: does the CONTEST configuration generalize?

Usage:
  python3 run_frontier_generalization_eval.py [--out ../eval-scorecard/frontier-generalization-runs.json]

Question (maximizer iteration 33, item-4 polish): every generalization
pass in this repo (iterations 15/19/23: ledgerlite, textkit, gradebook)
ran under the Oct 25 kept split config, and every all-frontier pass
(iterations 31/32) ran only on the seeded demo set. So the contest
configuration itself -- all four roles on muse-wonder-1.0, per
Joseph's Oct 26 directive -- has never been measured on a codebase
outside the seeded set. This runner closes exactly that gap with the
hardest existing generalization target: generalization3/gradebook,
whose issue carries TWO defects in TWO production modules
(weighted_mean divides by len(values) instead of the weight sum;
letter_grade uses > 90 instead of >= 90), 12-test baseline.

Method: identical to run_generalization3_eval.py -- pipeline.run
against a fresh git-initialized COPY of ../generalization3/ (the
vendored copy is never run in place and was not tuned after any run),
ConnectorClient (Meta Model API via the custom.meta-model-api
connector, no env key), except the configuration is the contest
configuration: every role on muse-wonder-1.0, muse-spark-1.3
configured only as availability fallback. One run, reported honestly
whatever the outcome. The iteration-23 split-config summary is read
from eval-scorecard/generalization3-runs.json at build time so the
comparison is computed from both measured records.

Independent probe: the same 8 checks written for iteration 23 (NOT by
the pipeline, NOT part of its regression tests) import the fixed
copy's gradebook package and verify both defects and both end-to-end
combinations. The run only counts as passed if the pipeline passes
AND every probe check passes.
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
GEN_REPO = ROOT / "generalization3"
ISSUE_FILE = GEN_REPO / "issue.json"
PRIOR_RECORD = ROOT / "eval-scorecard" / "generalization3-runs.json"
MODEL = "muse-wonder-1.0"
FALLBACK = "muse-spark-1.3"
CONFIG_LABEL = ("all-frontier (contest config): every role "
                "muse-wonder-1.0, muse-spark-1.3 configured only as "
                "availability fallback")
PRODUCTION_FILES = ["gradebook/averages.py", "gradebook/letters.py"]


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


def run_probe(repo):
    """Independent checks against the (possibly fixed) copy at `repo`.

    Identical to the iteration-23 probe: written for that evaluation,
    the pipeline never sees them.
    """
    for name in list(sys.modules):
        if name == "gradebook" or name.startswith("gradebook."):
            del sys.modules[name]
    sys.path.insert(0, str(repo))
    try:
        averages = importlib.import_module("gradebook.averages")
        letters = importlib.import_module("gradebook.letters")
        report = importlib.import_module("gradebook.report")
        cases = [
            ("weighted_mean([80, 100], [3, 1])", 85.0,
             averages.weighted_mean([80, 100], [3, 1])),
            ("weighted_mean([70, 90], [1, 3])", 85.0,
             averages.weighted_mean([70, 90], [1, 3])),
            ("weighted_mean([80, 100], [1, 1]) (unchanged case)", 90.0,
             averages.weighted_mean([80, 100], [1, 1])),
            ("letter_grade(90)", "A", letters.letter_grade(90)),
            ("letter_grade(89.9)", "B", letters.letter_grade(89.9)),
            ("letter_grade(95) (unchanged case)", "A",
             letters.letter_grade(95)),
            ("final_letter([90, 90], [1, 1])", "A",
             report.final_letter([90, 90], [1, 1])),
            ("final_letter([80, 100], [3, 1])", "B",
             report.final_letter([80, 100], [3, 1])),
        ]
        return [{"check": name, "expected": expected, "actual": actual,
                 "passed": actual == expected}
                for name, expected, actual in cases]
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
    row = {"slug": "frontier-generalization-gradebook",
           "issue": issue["title"],
           "mode": "live-frontier-generalization3",
           "config": CONFIG_LABEL,
           "target_codebase": "generalization3/ (gradebook package)"}
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
                        "probe": run_probe(repo),
                        "probe_passed": False})
            return row, started
        except Exception as e:  # a failed live run is a measured result
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
                        "cost": None,
                        "pr_produced": False,
                        "probe": run_probe(repo),
                        "probe_passed": False})
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
        "source": "eval-scorecard/generalization3-runs.json "
                  "(maximizer iteration 23, kept split config)",
        "config": doc["config"],
        "outcome": r["outcome"],
        "tests_before": r["tests_before"],
        "tests_after": r["tests_after"],
        "test_growth": doc["summary"]["test_growth"],
        "wall_clock_seconds": r["wall_clock_seconds"],
        "total_usd_est": (r.get("cost") or {}).get("total_usd_est"),
        "probe_passed": r["probe_passed"],
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
        "record": "Frontier generalization eval -- the contest "
                  "configuration (all roles muse-wonder-1.0) run live "
                  "on the unseen gradebook codebase, Oct 26, 2026 "
                  "(maximizer iteration 33)",
        "method": "pipeline.run (guardrail -> triage -> plan -> code "
                  "-> tests -> review) against a fresh git-initialized "
                  "copy of generalization3/ (gradebook), "
                  "ConnectorClient (Meta Model API via the "
                  "custom.meta-model-api connector, no env key), "
                  "all-frontier contest config, plus the iteration-23 "
                  "independent probe of both defects run against the "
                  "fixed copy afterwards. The vendored target was "
                  "created for iteration 23, was never run under the "
                  "all-frontier configuration before this run, and "
                  "was not tuned after the run. Prior split-config "
                  "summary read from "
                  "eval-scorecard/generalization3-runs.json. Costs "
                  "are character estimates at wonder's published "
                  "prices ($4/$20 per 1M in/out, daas/cost.py).",
        "config": CONFIG_LABEL,
        "model": MODEL,
        "fallback_model": FALLBACK,
        "target": {
            "codebase": "generalization3/",
            "package": "gradebook",
            "baseline_tests": 12,
            "defects": [
                "gradebook/averages.py weighted_mean divides by "
                "len(values) instead of the sum of the weights",
                "gradebook/letters.py letter_grade uses > 90 "
                "instead of >= 90",
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
    pcost = (f"${p['total_usd_est']:.4f}"
             if p["total_usd_est"] is not None else "n/a")
    probe_passed_count = sum(1 for c in r["probe"] if c["passed"])
    lines = [
        "# Frontier generalization -- the contest configuration on an "
        "unseen codebase (Oct 26, 2026)",
        "",
        "Maximizer iteration 33. Every earlier generalization pass "
        "(ledgerlite, textkit, gradebook) ran under the Oct 25 kept "
        "split config, and every all-frontier pass (iterations 31/32) "
        "ran only on the seeded demo set -- so the contest "
        "configuration (all four roles on `muse-wonder-1.0`, per "
        "Joseph's Oct 26 directive; `muse-spark-1.3` configured only "
        "as availability fallback) had never been measured outside "
        "the seeded set. This file is that measurement: the hardest "
        "existing generalization target, run live under the contest "
        "configuration, reported as measured.",
        "",
        "## The target",
        "",
        "`generalization3/` vendors **gradebook** (12-test baseline): "
        "two defects in two production modules -- `weighted_mean` in "
        "`gradebook/averages.py` divides by `len(values)` instead of "
        "the sum of the weights (baseline repro 170.0, expected "
        "85.0), and `letter_grade` in `gradebook/letters.py` uses "
        "`> 90` instead of `>= 90` (baseline repro `letter_grade(90)` "
        "returns 'B', expected 'A'). The vendored copy was not tuned "
        "after the run and still reproduces both bugs in place; the "
        "pipeline ran against a fresh git-initialized copy.",
        "",
        "## Measured live run (connector, all-frontier contest config)",
        "",
        f"- Outcome: **{r['outcome']}** (pipeline: "
        f"{r['pipeline_outcome']}; independent probe: "
        f"{probe_passed_count}/{len(r['probe'])} checks passed)",
        f"- Tests: {r['tests_before']} -> {r['tests_after']} "
        f"(growth +{s['test_growth']})" if s["test_growth"] is not None
        else "- Tests: n/a (run did not complete the tests stage)",
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
        "## Comparison with the same target under the split (iteration 23)",
        "",
        f"- Split pass (source: {p['source']}): outcome "
        f"{p['outcome']}, tests {p['tests_before']} -> "
        f"{p['tests_after']} (+{p['test_growth']}), "
        f"{p['wall_clock_seconds']}s, est. {pcost}, probe passed: "
        f"{p['probe_passed']}.",
        f"- All-frontier pass (this run): outcome {r['outcome']}, "
        f"tests {r['tests_before']} -> {r['tests_after']}, "
        f"{r['wall_clock_seconds']}s, est. {cost}, probe passed: "
        f"{r['probe_passed']}.",
        "",
    ]
    if s["passed"]:
        verdict = ("The contest configuration generalized: the "
                   "all-frontier pipeline passed end to end on an "
                   "unseen multi-file codebase and the independent "
                   "probe passed, so the frontier record is no longer "
                   "seeded-set-only. This is one run on one synthetic "
                   "target already used for the split-config "
                   "generalization record -- it does not add a new "
                   "codebase or a real-team claim.")
    else:
        verdict = ("The contest configuration did NOT fully pass on "
                   "this target as measured above; that outcome "
                   "stands as recorded, and no generalization claim "
                   "for the all-frontier configuration is made from "
                   "this run.")
    lines += [
        f"Verdict (computed from the measured run): {verdict}",
        "",
        "Honest limits: one live run, on a small synthetic package "
        "written for this evaluation family (n=1 issue); no real "
        "users/backlog; review time remains the IMPACT_MODEL.md "
        "assumption. Costs are character estimates, not "
        "provider-reported usage. No tool calling or "
        "responses-endpoint surface is claimed -- the connector "
        "helper offers chat completions only.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(
        ROOT / "eval-scorecard" / "frontier-generalization-runs.json"))
    args = ap.parse_args()
    doc = build_record()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    (out.parent / "FRONTIER_GENERALIZATION.md").write_text(render_md(doc))
    print(json.dumps({"summary": doc["summary"],
                      "models_by_role": doc["runs"][0]["models_by_role"],
                      "fallback_stats": doc["runs"][0]["fallback_stats"],
                      "retry_stats": doc["runs"][0]["retry_stats"]},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
