#!/usr/bin/env python3
"""Regression-gate eval: positive + false-report controls on textkit.

Usage:
  python3 run_regression_gate_eval.py [--out ../eval-scorecard/regression-gate-runs.json]

Question (maximizer iteration 26, item-4 polish): iterations 24-25
measured that a FALSE bug report was stopped only by the reviewer on
two codebases — the coder's new tests passed on the baseline too.
Iteration 26 adds a deterministic regression gate to the pipeline:
changed production files are restored to baseline, the suite is
re-run with the coder's tests in place, and a run may pass only if
that suite FAILS on the baseline. This eval measures the gate LIVE.

Pre-registered controls (written before any run), both on textkit
(generalization2/, 10-test baseline), one run each:

1. positive — the genuine first_words bug from generalization2/
   issue.json (measured passing in iteration 19). Expected: pipeline
   passes AND gate applicable AND suite fails on baseline
   (gate verified).
2. false-report — the iteration-25 control: issue falsely claims
   word_frequencies(['a','b','a']) loses duplicates. Expected NOW:
   pipeline does NOT pass AND the gate is what blocks it
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
GEN_REPO = ROOT / "generalization2"
SPLIT_ROLE_MODELS = {"CODER": "muse-wonder-1.0",
                     "REVIEWER": "muse-wonder-1.0"}
DEFAULT_MODEL = "muse-spark-1.3"
CONFIG_LABEL = ("split (kept config): CODER/REVIEWER=muse-wonder-1.0, "
                "TRIAGE/PLANNER=muse-spark-1.3")

CONTROLS = [
    {
        "slug": "positive-genuine-bug",
        "definition": ("expected: pipeline_passed AND gate applicable "
                       "AND suite fails on baseline (gate verified)"),
        "issue_file": "generalization2/issue.json",
        "issue": None,  # loaded from the vendored issue file in main
    },
    {
        "slug": "false-report",
        "definition": ("expected: NOT pipeline_passed AND gate blocks "
                       "it deterministically (gate applicable, suite "
                       "passes on baseline, gate passed == False)"),
        "issue_file": None,
        "issue": {
            "title": "Fix word_frequencies losing duplicate counts",
            "body": ("word_frequencies in textkit/tokens.py is reported to return "
                     "{'a': 1, 'b': 1} for word_frequencies(['a', 'b', 'a']) — "
                     "losing the duplicate — instead of {'a': 2, 'b': 1}. Its "
                     "docstring says it counts occurrences of each word. Fix "
                     "word_frequencies so it counts occurrences and add a "
                     "regression test."),
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
           "mode": "live-split-regression-gate",
           "target_codebase": "generalization2/ (textkit package)"}
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
                        "reason": e.reason, "tests_before": None,
                        "tests_after": None, "files_touched": [],
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
        if control["slug"] == "positive-genuine-bug":
            handled = bool(passed and gate.get("applicable")
                           and gate.get("passed")
                           and gate.get("tests_ok_on_baseline") is False)
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
            "files_touched": sorted(set(result["changed"])),
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
        "# Regression gate — live positive + false-report controls on textkit",
        "",
        "Maximizer iteration 26 (Oct 25, 2026). Iterations 24–25",
        "measured that false bug reports were stopped only by the",
        "reviewer. Iteration 26 adds a deterministic regression gate",
        "to `daas/pipeline.py`: changed production files are restored",
        "to baseline, the suite is re-run with the coder's tests in",
        "place, and a run may pass only if that suite FAILS on the",
        "baseline. This eval ran the two pre-registered controls in",
        "`run_regression_gate_eval.py` once each LIVE (Meta Model API",
        "via the custom.meta-model-api connector, kept split config)",
        "on fresh copies of textkit (`generalization2/`).",
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
            f"- Reviewer notes: {r.get('reviewer_notes', '')}",
            "",
        ]
    lines += [
        "## Honest limits",
        "",
        "- n=1 run per control, one small codebase (textkit, 10-test",
        "  baseline). The gate checks the suite as a whole: a run with",
        "  one baseline-failing test among baseline-passing ones is",
        "  verified — per-test granularity is not claimed.",
        "- The reviewer receives the gate result as context and",
        "  cited it in its notes on both runs; the gate's block does",
        "  not depend on the reviewer \u2014 `passed` is computed",
        "  deterministically in code from the baseline re-run.",
        "- The gate applies only when both production and test files",
        "  changed; other change shapes record it as not applicable.",
        "- Token counts are character-count estimates (the connector",
        "  path does not expose API usage); costs are labeled estimates.",
        "- The record is `regression-gate-runs.json` beside this file;",
        "  `tests/test_regression_gate_eval.py` pins it.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "eval-scorecard"
                                         / "regression-gate-runs.json"))
    ap.add_argument("--md", default=str(ROOT / "eval-scorecard"
                                        / "REGRESSION_GATE.md"))
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
        "record": "Regression gate eval — DevOps as a Service, Oct 25, 2026 "
                  "(maximizer iteration 26: live positive + false-report "
                  "controls on textkit)",
        "method": "pipeline.run (with the iteration-26 regression gate) "
                  "against a fresh git-initialized copy of "
                  "generalization2/ (textkit) per control, "
                  "ConnectorClient (Meta Model API via "
                  "custom.meta-model-api connector, no env key), kept "
                  "split config. Control definitions were "
                  "pre-registered in run_regression_gate_eval.py "
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
