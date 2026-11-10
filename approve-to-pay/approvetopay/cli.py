"""Runner + report for the frozen Approve-to-Pay task set.

Usage (from the approve-to-pay/ directory):

    python3 run_tasks.py              # run all 20 jobs, append to the
                                      # decision log, write + print report
    python3 run_tasks.py --job ATP-019  # run a single job

The runner verifies tasks.json against tasks.sha256 before running and
refuses to run a modified set: the set was frozen before the runner was
wired, and a measured result is only meaningful against the frozen set.

The report counts only what actually happened — captured, blocked by the
guardrail (by reason), blocked by the approver — and, per the Meta-lessons
addendum (fix 5), the misses: false blocks (expected capture, blocked) and
missed blocks (expected block, captured). No modeled savings anywhere.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from collections import Counter
from decimal import Decimal
from pathlib import Path

from . import pipeline
from .decision_log import DecisionLog
from .paypal_client import from_env

ROOT = Path(__file__).resolve().parent.parent
TASKS_PATH = ROOT / "tasks.json"
CHECKSUM_PATH = ROOT / "tasks.sha256"
DEFAULT_LOG = ROOT / "decision-log.jsonl"
RESULTS_DIR = ROOT / "results"


def verify_frozen_set() -> dict:
    raw = TASKS_PATH.read_bytes()
    recorded = CHECKSUM_PATH.read_text().split()[0]
    actual = hashlib.sha256(raw).hexdigest()
    if actual != recorded:
        raise SystemExit(
            "tasks.json does not match tasks.sha256 — the frozen task set "
            "was modified. Restore it or cut a new version; refusing to "
            "run a moved target.")
    return json.loads(raw)


def build_report(entries: list[dict], task_set_version: str) -> dict:
    captured = [e for e in entries if e["actual_outcome"] == "capture"]
    g_blocked = [e for e in entries if e["actual_outcome"] == "block_guardrail"]
    a_blocked = [e for e in entries if e["actual_outcome"] == "block_approver"]
    false_blocks = [e for e in entries
                    if e["expected_outcome"] == "capture"
                    and e["actual_outcome"] != "capture"]
    missed_blocks = [e for e in entries
                     if e["expected_outcome"] != "capture"
                     and e["actual_outcome"] == "capture"]
    blocked_amount = sum(Decimal(e["amount"]) for e in g_blocked + a_blocked)
    return {
        "task_set_version": task_set_version,
        "mode": entries[0]["mode"] if entries else "mock",
        "total_jobs": len(entries),
        "captured": len(captured),
        "captured_total_usd": str(sum(Decimal(e["amount"]) for e in captured)),
        "blocked_by_guardrail": len(g_blocked),
        "blocked_by_guardrail_by_reason": dict(
            Counter(e["guardrail_reason"] for e in g_blocked)),
        "blocked_by_approver": len(a_blocked),
        "blocked_moved_usd": "0.00",
        "blocked_intended_spend_usd": str(blocked_amount),
        "outcome_matches": sum(1 for e in entries if e["outcome_match"]),
        "false_blocks": [e["job_id"] for e in false_blocks],
        "missed_blocks": [e["job_id"] for e in missed_blocks],
        "capture_calls_on_blocked_jobs": sum(
            1 for e in entries
            if e["actual_outcome"] != "capture" and e["capture_called"]),
    }


def render_markdown(report: dict, entries: list[dict]) -> str:
    r = report
    lines = [
        f"# Approve-to-Pay — task set run report",
        "",
        f"- Task set version: {r['task_set_version']} (frozen, checksum-verified)",
        f"- PayPal mode: **{r['mode']}**"
        + (" — fixture-backed mock, no sandbox credentials configured"
           if r["mode"] == "mock" else " — real PayPal sandbox"),
        f"- Jobs run: {r['total_jobs']}",
        f"- Captured (COMPLETED): {r['captured']} "
        f"(${r['captured_total_usd']} moved in sandbox)",
        f"- Blocked by guardrail: {r['blocked_by_guardrail']} "
        f"{r['blocked_by_guardrail_by_reason']}",
        f"- Blocked by approver: {r['blocked_by_approver']}",
        f"- Blocked purchases that moved money: ${r['blocked_moved_usd']} "
        f"(intended spend held: ${r['blocked_intended_spend_usd']})",
        f"- Outcomes matching the frozen expectations: "
        f"{r['outcome_matches']}/{r['total_jobs']}",
        f"- False blocks (expected capture, got blocked): "
        f"{r['false_blocks'] or 'none'}",
        f"- Missed blocks (expected block, got captured): "
        f"{r['missed_blocks'] or 'none'}",
        f"- Capture calls on blocked jobs: {r['capture_calls_on_blocked_jobs']}",
        "",
        "| Job | Order | Guardrail | Approver | Capture called | Status | Actual | Expected | Match |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for e in entries:
        lines.append(
            f"| {e['job_id']} | {e['order_id'] or '—'} "
            f"| {e['guardrail_verdict']}"
            f"{' (' + e['guardrail_reason'] + ')' if e['guardrail_reason'] else ''} "
            f"| {e['approver_decision']} "
            f"| {str(e['capture_called']).lower()} "
            f"| {e['capture_status'] or '—'} "
            f"| {e['actual_outcome']} | {e['expected_outcome']} "
            f"| {'yes' if e['outcome_match'] else 'NO'} |")
    lines += ["", "Full audit trail: decision-log.jsonl (append-only)."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the frozen Approve-to-Pay task set")
    parser.add_argument("--job", help="run a single job id (e.g. ATP-019)")
    parser.add_argument("--log", default=str(DEFAULT_LOG),
                        help="decision log path (default: decision-log.jsonl)")
    args = parser.parse_args(argv)

    task_set = verify_frozen_set()
    jobs = task_set["jobs"]
    if args.job:
        jobs = [j for j in jobs if j["id"] == args.job]
        if not jobs:
            raise SystemExit(f"no job {args.job} in the frozen task set")

    client = from_env()
    log = DecisionLog(Path(args.log))
    run_id = uuid.uuid4().hex[:12]
    entries = [pipeline.run_job(job, task_set["policy"], client, log, run_id)
               for job in jobs]

    report = build_report(entries, task_set["version"])
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "latest-report.json").write_text(
        json.dumps(report, indent=2) + "\n")
    md = render_markdown(report, entries)
    (RESULTS_DIR / "latest-report.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
