#!/usr/bin/env python3
"""Target-gate recheck: re-run ONLY the false-passed control, post-fix.

Usage:
  python3 run_target_gate_recheck.py [--out ../eval-scorecard/target-gate-recheck.json]

Maximizer iteration 27, following the iteration-24 pattern (the
measured failure record stands; a hardening change is validated by
re-running the exact measured failure once under the new code):

- The regression-gate-2 eval measured the gradebook `false-report`
  control as a FALSE PASS under the new name of an old problem: the
  issue falsely claimed simple_mean was broken; the coder instead
  fixed weighted_mean — a genuine bug in the same file — so the
  regression gate verified a real change (suite fails on baseline),
  the reviewer approved, tests grew 12 -> 16, and the run PASSED
  without touching the function the issue was about. That record
  (regression-gate2-runs.json) is NOT altered.
- daas/pipeline.py gained a deterministic issue-target gate: when
  the issue names existing repo functions, a run may pass only if
  the production change actually modifies at least one of them.
- This runner re-runs that one control once, live, under the kept
  split config. Handled (pre-registered for this recheck) = the run
  does NOT pass AND the target gate is applicable AND blocks it
  (target_gate.passed == False), whatever the reviewer verdict is.
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
import run_regression_gate2_eval as base  # noqa: E402
from daas import pipeline  # noqa: E402
from daas.llm import ConnectorClient, resolve_model  # noqa: E402

ROOT = base.ROOT
GEN_REPO = base.GEN_REPO
CONTROL = [c for c in base.CONTROLS if c["slug"] == "false-report"][0]


class RecordingClient(base.RecordingClient):
    pass


def run_one(client_factory):
    issue = CONTROL["issue"]
    row = {"slug": CONTROL["slug"], "issue": issue["title"],
           "definition": ("recheck handled = NOT pipeline_passed AND "
                          "target gate applicable AND target gate "
                          "passed == False"),
           "mode": "live-split-target-gate-recheck",
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
                        "handled": False, "reason": e.reason,
                        "tests_before": None, "tests_after": None,
                        "files_touched": [], "regression_gate": None,
                        "target_gate": events.get("target_gate"),
                        "wall_clock_seconds": wall,
                        "model_calls": len(client.calls),
                        "models_by_role": {c["role"]: c["model"]
                                           for c in client.calls},
                        "cost": getattr(e, "cost", None)})
            return row, started
        wall = round(time.perf_counter() - t0, 2)
        review = events.get("review", {})
        gate = result.get("regression_gate") or {}
        tgate = result.get("target_gate") or {}
        passed = bool(result["passed"])
        handled = bool(not passed and tgate.get("applicable")
                       and tgate.get("passed") is False)
        row.update({
            "outcome": "passed" if passed else "failed",
            "pipeline_passed": passed, "handled": handled,
            "tests_before": result["tests_before"],
            "tests_after": result["tests_after"],
            "tests_ok": result["tests_ok"],
            "files_touched": sorted(set(result["changed"])),
            "unexpected_files": result["unexpected_files"],
            "regression_gate": gate, "target_gate": tgate,
            "wall_clock_seconds": wall,
            "model_calls": len(client.calls),
            "models_by_role": {c["role"]: c["model"] for c in client.calls},
            "reviewer_verdict": review.get("verdict"),
            "reviewer_notes": review.get("notes", ""),
            "cost": result.get("cost"),
        })
        return row, started


def render_md(doc):
    r = doc["runs"][0]
    tgate = r.get("target_gate") or {}
    lines = [
        "# Target-gate recheck — the off-target false pass, re-run post-fix",
        "",
        "Maximizer iteration 27 (Oct 26, 2026). The regression-gate-2",
        "eval (`REGRESSION_GATE2.md`) measured the gradebook",
        "`false-report` control as a **false pass**: for a false claim",
        "about `simple_mean`, the coder fixed the genuine",
        "`weighted_mean` bug in the same file instead, the regression",
        "gate verified that real change, the reviewer approved, tests",
        "grew 12 → 16, and the run passed without touching the",
        "function the issue was about. That record stands unaltered.",
        "",
        "Fix: a deterministic issue-target gate in `daas/pipeline.py`",
        "— when the issue names existing repo functions, a run may",
        "pass only if the production change actually modifies at",
        "least one of them (function source segments compared between",
        "the baseline and after snapshots; not applicable when the",
        "issue names no existing function), pinned by",
        "`tests/test_target_gate.py`.",
        "",
        f"**Recheck result: outcome `{r['outcome']}`, handled: "
        f"{'yes' if r['handled'] else 'NO'}** "
        f"(wall clock {r['wall_clock_seconds']}s, "
        f"tests {r.get('tests_before')} → {r.get('tests_after')}, "
        f"reviewer {r.get('reviewer_verdict')}).",
        "",
        f"- Target gate: {tgate}",
        f"- Regression gate: {r.get('regression_gate')}",
        "",
        ("In this re-run the coder stayed ON target (the "
         "`simple_mean` segment changed), so the target gate passed "
         "and there was no off-target drift for it to block; the run "
         "was instead blocked deterministically by the regression "
         "gate (the coder's behavior-preserving refactor left the "
         "suite passing on the baseline) and the reviewer requested "
         "changes. The recheck's pre-registered handled definition "
         "required a TARGET-gate block specifically, so it records "
         "handled: NO — while the combined gate system did stop the "
         "false report. The off-target shape itself is blocked "
         "deterministically in the test-pinned mock/helper tests "
         "(`tests/test_target_gate.py`); whether a live coder drifts "
         "off target varies run to run."
         if tgate.get("passed") and not (r.get("regression_gate") or {}).get("passed")
         else "The blocking gate for this re-run is recorded above."),
        f"- Files touched: {r.get('files_touched') or 'none'}",
        f"- Reviewer notes: {r.get('reviewer_notes', '')}",
        "",
        "## Honest limits",
        "",
        "- One re-run of one control under the new code; the gate is",
        "  also test-pinned in mock mode (genuine Tier-1 passes, an",
        "  off-target stub client cannot pass).",
        "- The gate only fires when the issue names an existing",
        "  function as a whole word; issues that describe behaviour",
        "  without naming a function are not applicable and rely on",
        "  the other gates and the reviewer, as before.",
        "- Token counts are character-count estimates (the connector",
        "  path does not expose API usage); costs are labeled estimates.",
        "- The record is `target-gate-recheck.json` beside this file;",
        "  `tests/test_regression_gate2_eval.py` pins both records.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "eval-scorecard"
                                         / "target-gate-recheck.json"))
    ap.add_argument("--md", default=str(ROOT / "eval-scorecard"
                                        / "TARGET_GATE.md"))
    args = ap.parse_args()

    def factory():
        return RecordingClient(ConnectorClient(
            model=base.DEFAULT_MODEL,
            role_models=dict(base.SPLIT_ROLE_MODELS)))

    row, started = run_one(factory)
    row["started_at"] = started.isoformat()
    print(f"{row['slug']}: outcome={row['outcome']} "
          f"handled={row.get('handled')} wall={row['wall_clock_seconds']}s "
          f"tests={row.get('tests_before')}->{row.get('tests_after')} "
          f"target_gate={row.get('target_gate')}")
    doc = {
        "record": "Target gate recheck — DevOps as a Service, Oct 26, 2026 "
                  "(maximizer iteration 27: the regression-gate-2 "
                  "false-report control re-run once under the new "
                  "issue-target gate)",
        "method": "pipeline.run (with the iteration-27 issue-target "
                  "gate) against a fresh git-initialized copy of "
                  "generalization3/ (gradebook), ConnectorClient (Meta "
                  "Model API via custom.meta-model-api connector, no "
                  "env key), kept split config. One run, reported "
                  "honestly whatever the outcome; the original "
                  "regression-gate2 record is not altered.",
        "config": base.CONFIG_LABEL,
        "started_at": started.isoformat(),
        "runs": [row],
        "summary": {"total": 1, "handled": 1 if row["handled"] else 0,
                    "all_handled": bool(row["handled"])},
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    Path(args.md).write_text(render_md(doc))
    print(f"summary: {doc['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
