#!/usr/bin/env python3
"""Plan-gate recheck: re-run ONLY the false-passed control, post-fix.

Usage:
  python3 run_plan_gate_recheck.py [--out ../eval-scorecard/negative-controls-recheck.json]

Maximizer iteration 24, following the iteration-22 pattern (the
measured failure record stands; a hardening change is validated by
re-running the exact measured failure once under the new code):

- The negative-controls eval measured the `nonexistent-target`
  control as a FALSE PASS: the pipeline invented
  gradebook/statistics.py, tests grew 12 -> 18, reviewer approved.
  That record (negative-controls-runs.json) is NOT altered.
- daas/pipeline.py gained a deterministic plan gate: for a bug
  report, a plan naming a non-test production file absent from the
  repo tree escalates before the coder runs (features exempt).
- This runner re-runs that one control once, live, under the kept
  split config, and records the outcome as measured.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import run_negative_controls_eval as controls  # noqa: E402
from daas.llm import ConnectorClient  # noqa: E402


def render_md(doc):
    r = doc["runs"][0]
    lines = [
        "# Plan-gate recheck — the false-passed control, re-run post-fix",
        "",
        "Maximizer iteration 24 (Oct 25, 2026). The negative-controls",
        "eval (`NEGATIVE_CONTROLS.md`) measured the `nonexistent-target`",
        "control as a **false pass**: the pipeline invented",
        "`gradebook/statistics.py` to \"fix\" a `median()` that does not",
        "exist, tests grew 12 → 18, and the reviewer approved. That",
        "record stands unaltered.",
        "",
        "Fix: a deterministic plan gate in `daas/pipeline.py` — for a",
        "bug report, a plan naming a non-test production file that is",
        "not in the repo tree escalates BEFORE the coder runs (feature",
        "requests exempt; new test files exempt), pinned by",
        "`tests/test_plan_gate.py`.",
        "",
        f"**Recheck result: outcome `{r['outcome']}`, handled: "
        f"{'yes' if r['handled'] else 'NO'}** "
        f"(wall clock {r['wall_clock_seconds']}s, "
        f"model calls {r['model_calls']}).",
        "",
    ]
    if r.get("reason"):
        lines += [f"Escalation reason: {r['reason']}", ""]
    lines += [
        "## Honest limits",
        "",
        "- One re-run of one control under the new code; the gate is",
        "  deterministic given the plan, but whether the planner names",
        "  the invented file can vary by run — the unit tests pin the",
        "  gate itself, this record shows one live pass through it.",
        "- The original false-pass record is not erased or re-scored",
        "  away: it is why the gate exists.",
        "- Record: `negative-controls-recheck.json` beside this file;",
        "  pinned by `tests/test_negative_controls.py`.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(controls.ROOT / "eval-scorecard"
                                         / "negative-controls-recheck.json"))
    ap.add_argument("--md", default=str(controls.ROOT / "eval-scorecard"
                                        / "PLAN_GATE.md"))
    args = ap.parse_args()

    def factory():
        return controls.RecordingClient(ConnectorClient(
            model=controls.DEFAULT_MODEL,
            role_models=dict(controls.SPLIT_ROLE_MODELS)))

    control = [c for c in controls.CONTROLS
               if c["slug"] == "nonexistent-target"][0]
    row, started = controls.run_one(control, factory)
    row["started_at"] = started.isoformat()
    doc = {
        "record": "Plan-gate recheck — DevOps as a Service, Oct 25, 2026 "
                  "(maximizer iteration 24: post-fix re-validation of the "
                  "false-passed negative control)",
        "method": "Same control, same target copy method, same kept split "
                  "config as negative-controls-runs.json; run once after "
                  "the deterministic plan gate landed in daas/pipeline.py. "
                  "The original false-pass record is unchanged.",
        "config": controls.CONFIG_LABEL,
        "started_at": row["started_at"],
        "runs": [row],
        "summary": {"handled": bool(row["handled"]),
                    "outcome": row["outcome"]},
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    Path(args.md).write_text(render_md(doc))
    print(f"recheck: outcome={row['outcome']} handled={row['handled']} "
          f"wall={row['wall_clock_seconds']}s calls={row['model_calls']} "
          f"reason={row.get('reason', '')[:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
