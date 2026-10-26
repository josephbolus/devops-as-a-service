#!/usr/bin/env python3
"""Regression-gate eval 2: positive (multi-file) + false-report on gradebook.

Usage:
  python3 run_regression_gate2_eval.py [--out ../eval-scorecard/regression-gate2-runs.json]

Question (maximizer iteration 27, item-4 polish): iteration 26
validated the deterministic regression gate LIVE on ONE codebase
(textkit) with n=1 controls, and every gate validation so far was a
single-production-file change. Does the gate behave the same on a
SECOND codebase (gradebook, generalization3/, 12-test baseline),
including when the genuine fix touches TWO production files (the
gate must restore BOTH to baseline, see the suite fail, and restore
both fixes)?

Pre-registered controls (written before any run), one run each:

1. positive-genuine-multi-file — the genuine two-defect issue from
   generalization3/issue.json (measured passing in iteration 23).
   Expected: pipeline passes AND gate applicable AND gate passed
   (suite fails on baseline) AND both production files touched.
2. false-report — the iteration-24 control: issue falsely claims
   simple_mean([80, 90, 100]) returns the first element. Expected
   NOW: pipeline does NOT pass AND the gate blocks it
   deterministically (gate applicable, suite passes on baseline,
   gate passed == False), whatever the reviewer verdict is.

One run per control, reported honestly whatever the outcome.
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
from daas.llm import ConnectorClient, resolve_model  # noqa: E402

HERE = Path(__file__).parent
ROOT = HERE.parent
GEN_REPO = ROOT / "generalization3"
SPLIT_ROLE_MODELS = {"CODER": "muse-wonder-1.0",
                     "REVIEWER": "muse-wonder-1.0"}
DEFAULT_MODEL = "muse-spark-1.3"
CONFIG_LABEL = ("split (kept config): CODER/REVIEWER=muse-wonder-1.0, "
                "TRIAGE/PLANNER=muse-spark-1.3")
PRODUCTION_FILES = ["gradebook/averages.py", "gradebook/letters.py"]

CONTROLS = [
    {
        "slug": "positive-genuine-multi-file",
        "definition": ("expected: pipeline_passed AND gate applicable "
                       "AND gate passed (suite fails on baseline) AND "
                       "both production files touched"),
        "issue_file": "generalization3/issue.json",
        "issue": None,  # loaded from the vendored issue file in main
    },
    {
        "slug": "false-report",
        "definition": ("expected: NOT pipeline_passed AND gate blocks "
                       "it deterministically (gate applicable, suite "
                       "passes on baseline, gate passed == False)"),
        "issue_file": None,
        "issue": {
            "title": "Fix simple_mean returning the first element instead of the mean",
            "body": ("simple_mean in gradebook/averages.py is reported to return "
                     "80.0 for simple_mean([80, 90, 100]) — the first element — "
                     "instead of the arithmetic mean 90.0. Its docstring "
                     "specifies the arithmetic mean of the scores, with an "
                     "empty sequence giving 0.0. Fix simple_mean so it returns "
                     "the arithmetic mean and add a regression test."),
        },
    },
]


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


def run_one(control, client_factory):
    issue = control["issue"]
    row = {"slug": control["slug"], "issue": issue["title"],
           "definition": control["definition"],
           "mode": "live-split-regression-gate2",
           "target_codebase": "generalization3/ (gradebook package)"}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        repo = tmp / "repo"
        shutil.copytree(GEN_REPO, repo,
                        ignore=shutil.ignore_patterns("__pycache__"))
        (repo / "issue.json").unlink(missing_ok=True)
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
            row.update({"outcome": "escalated", "pipeline_passed": False,
                        "handled": False,
                        "reason": e.reason, "tests_before": None,
                        "tests_after": None, "files_touched": [],
                        "production_files_touched": [],
                        "regression_gate": None,
                        "wall_clock_seconds": wall,
                        "model_calls": len(client.calls),
                        "models_by_role": {c["role"]: c["model"]
                                           for c in client.calls},
                        "cost": getattr(e, "cost", None)})
            return row, started
        wall = round(time.perf_counter() - t0, 2)
        review = events.get("review", {})
        gate = result.get("regression_gate") or {}
        passed = bool(result["passed"])
        touched = sorted(set(result["changed"]))
        prod_touched = [f for f in touched if f in PRODUCTION_FILES]
        if control["slug"] == "positive-genuine-multi-file":
            handled = bool(passed and gate.get("applicable")
                           and gate.get("passed")
                           and gate.get("tests_ok_on_baseline") is False
                           and prod_touched == PRODUCTION_FILES)
        else:
            handled = bool(not passed and gate.get("applicable")
                           and gate.get("passed") is False
                           and gate.get("tests_ok_on_baseline") is True)
        row.update({
            "outcome": "passed" if passed else "failed",
            "pipeline_passed": passed, "handled": handled,
            "tests_before": result["tests_before"],
            "tests_after": result["tests_after"],
            "tests_ok": result["tests_ok"],
            "files_touched": touched,
            "production_files_touched": prod_touched,
            "unexpected_files": result["unexpected_files"],
            "regression_gate": gate,
            "wall_clock_seconds": wall,
            "model_calls": len(client.calls),
            "models_by_role": {c["role"]: c["model"] for c in client.calls},
            "reviewer_verdict": review.get("verdict"),
            "reviewer_notes": review.get("notes", ""),
            "cost": result.get("cost"),
        })
        return row, started


def render_md(doc):
    lines = [
        "# Regression gate 2 — live multi-file positive + false-report controls on gradebook",
        "",
        "Maximizer iteration 27 (Oct 26, 2026). Iteration 26 validated",
        "the deterministic regression gate live on one codebase",
        "(textkit) with single-file changes. This eval ran the two",
        "pre-registered controls in `run_regression_gate2_eval.py`",
        "once each LIVE (Meta Model API via the custom.meta-model-api",
        "connector, kept split config) on fresh copies of gradebook",
        "(`generalization3/`, 12-test baseline) — including the first",
        "multi-file gate validation: the genuine fix touches two",
        "production modules, so the gate must restore both to",
        "baseline, see the suite fail, and restore both fixes.",
        "",
        f"**Result: {doc['summary']['handled']}/{doc['summary']['total']} "
        f"controls behaved as pre-registered.**",
        "",
        "| Control | Pipeline outcome | Gate | Tests | Wall clock | Est. cost |",
        "|---|---|---|---|---|---|",
    ]
    for r in doc["runs"]:
        gate = r.get("regression_gate") or {}
        gate_s = ("n/a" if not gate else
                  "verified (fails on baseline)" if gate.get("passed")
                  and gate.get("applicable") else
                  "BLOCKED (passes on baseline)" if gate.get("applicable")
                  else "not applicable")
        tests = (f"{r['tests_before']} → {r['tests_after']}"
                 if r.get("tests_before") is not None else "—")
        cost = (f"${r['cost']['total_usd_est']:.4f}"
                if r.get("cost") and isinstance(r.get("cost"), dict)
                and "total_usd_est" in r["cost"] else "—")
        lines.append(f"| {r['slug']} | {r['outcome']} | {gate_s} | "
                     f"{tests} | {r['wall_clock_seconds']}s | {cost} |")
    lines += ["", "## Per-control detail", ""]
    for r in doc["runs"]:
        lines += [
            f"### {r['slug']}",
            "",
            f"- Issue: {r['issue']}",
            f"- Pre-registered expectation: {r['definition']}",
            f"- Pipeline outcome: **{r['outcome']}** "
            f"(reviewer: {r.get('reviewer_verdict')}); "
            f"as pre-registered: **{'yes' if r.get('handled') else 'NO'}**",
            f"- Regression gate: {r.get('regression_gate')}",
            f"- Files touched: {r['files_touched'] or 'none'}",
            f"- Production files touched: {r.get('production_files_touched') or 'none'}",
            f"- Reviewer notes: {r.get('reviewer_notes', '')}",
            "",
        ]
    lines += [
        "## Honest limits",
        "",
        "- n=1 run per control. Combined with iteration 26, the gate",
        "  now has live controls on two codebases (textkit and",
        "  gradebook), including one multi-file fix — still small",
        "  synthetic packages, no real-team workload.",
        "- The gate checks the suite as a whole: a run with one",
        "  baseline-failing test among baseline-passing ones is",
        "  verified — per-test granularity is not claimed.",
        "- The reviewer receives the gate result as context; the",
        "  gate's block does not depend on the reviewer — `passed` is",
        "  computed deterministically in code from the baseline re-run.",
        "- The gate applies only when both production and test files",
        "  changed; other change shapes record it as not applicable.",
        "- Token counts are character-count estimates (the connector",
        "  path does not expose API usage); costs are labeled estimates.",
        "- The record is `regression-gate2-runs.json` beside this file;",
        "  `tests/test_regression_gate2_eval.py` pins it. The",
        "  iteration-26 textkit record stands unaltered.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "eval-scorecard"
                                         / "regression-gate2-runs.json"))
    ap.add_argument("--md", default=str(ROOT / "eval-scorecard"
                                        / "REGRESSION_GATE2.md"))
    args = ap.parse_args()
    for c in CONTROLS:
        if c["issue"] is None:
            c["issue"] = json.loads((ROOT / c["issue_file"]).read_text())

    def factory():
        return RecordingClient(ConnectorClient(
            model=DEFAULT_MODEL, role_models=dict(SPLIT_ROLE_MODELS)))

    runs, started_first = [], None
    for control in CONTROLS:
        row, started = run_one(control, factory)
        row["started_at"] = started.isoformat()
        if started_first is None:
            started_first = started
        runs.append(row)
        print(f"{row['slug']}: outcome={row['outcome']} "
              f"handled={row.get('handled')} wall={row['wall_clock_seconds']}s "
              f"tests={row.get('tests_before')}->{row.get('tests_after')} "
              f"gate={row.get('regression_gate')}")
    handled = sum(1 for r in runs if r.get("handled"))
    doc = {
        "record": "Regression gate eval 2 — DevOps as a Service, Oct 26, 2026 "
                  "(maximizer iteration 27: live multi-file positive + "
                  "false-report controls on gradebook)",
        "method": "pipeline.run (with the iteration-26 regression gate) "
                  "against a fresh git-initialized copy of "
                  "generalization3/ (gradebook) per control, "
                  "ConnectorClient (Meta Model API via "
                  "custom.meta-model-api connector, no env key), kept "
                  "split config. Control definitions were "
                  "pre-registered in run_regression_gate2_eval.py "
                  "before the runs; one run per control.",
        "config": CONFIG_LABEL,
        "started_at": started_first.isoformat() if started_first else None,
        "runs": runs,
        "summary": {"total": len(runs), "handled": handled,
                    "all_handled": handled == len(runs)},
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    Path(args.md).write_text(render_md(doc))
    print(f"summary: {doc['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
