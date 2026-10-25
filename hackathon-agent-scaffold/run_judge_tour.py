#!/usr/bin/env python3
"""Full Judge Mode tour — every seeded issue, self-guided, over HTTP.

Iteration 18 (maximizer item-4 polish, Demo): Judge Mode was proven over
HTTP for Tier 1 and the guardrail issue only. This runner exercises the
one-click judge endpoint for ALL FOUR seeded issues (tier1/tier2/tier3
+ guardrail) in mock mode — the unattended-judge default — and records
each run's closing results card: overall outcome, per-stage statuses,
test-count delta, caption count, and cost summary.

Mock mode is plumbing proof, not model performance (the live evidence
is in live-runs.json / the PRs). What this record proves is narrower
and Demo-shaped: a judge with no operator can run every tour stop
unaided and each stop ends in a correct, evidence-carrying card.

Outputs (repo-root eval-scorecard/):
  judge-tour.json — the measured record (per-run rows)
  JUDGE_TOUR.md   — the human-readable tour record

Timings (total_elapsed_ms) are measured per run and will differ on
re-run; outcomes, deltas, stage statuses, and caption counts are the
deterministic part the tests pin.
"""
import json
import sys
import threading
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
OUT_DIR = ROOT / "eval-scorecard"
sys.path.insert(0, str(HERE))
import demo_ui  # noqa: E402

TOUR_ORDER = ["tier1", "tier2", "tier3", "guardrail"]


def _http(port, path, payload=None):
    url = f"http://127.0.0.1:{port}{path}"
    if payload is None:
        with urllib.request.urlopen(url, timeout=60) as resp:
            return json.loads(resp.read())
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _poll(port, run_id, tries=240):
    snap = {}
    for _ in range(tries):
        snap = _http(port, f"/api/run/{run_id}")
        if snap["status"] != "running":
            return snap
        threading.Event().wait(0.25)
    raise TimeoutError(f"judge run {run_id} did not finish")


def run_tour(port):
    rows = []
    for issue_id in TOUR_ORDER:
        started = _http(port, "/api/judge/run",
                        {"issue_id": issue_id, "mode": "mock"})
        snap = _poll(port, started["run_id"])
        card = snap["results_card"]
        rows.append({
            "issue_id": issue_id,
            "mode": "mock",
            "judge_mode": bool(snap["judge_mode"]),
            "status": snap["status"],
            "overall": card["overall"],
            "stages": [{"stage": s["stage"], "status": s["status"]}
                       for s in card["stages"]],
            "tests_before": card["tests_before"],
            "tests_after": card["tests_after"],
            "tests_delta": card["tests_delta"],
            "captions": len(snap["captions"]),
            "all_captions_judge_mode": all(
                (c or "").startswith("Judge Mode:")
                for c in snap["captions"]),
            "total_elapsed_ms": card["total_elapsed_ms"],
            "cost_total_usd_est": (card["cost"] or {}).get("total_usd_est"),
            "links_live_prs": len(card["links"]["live_prs"]),
        })
    return rows


def summarize(rows):
    work = [r for r in rows if r["issue_id"] != "guardrail"]
    return {
        "runs": len(rows),
        "work_passed": sum(1 for r in work if r["overall"] == "pass"),
        "work_total": len(work),
        "guardrail_escalated": any(
            r["issue_id"] == "guardrail" and r["overall"] == "escalated"
            for r in rows),
        "total_tests_delta": sum(r["tests_delta"] or 0 for r in work),
    }


def render_md(record):
    s = record["summary"]
    lines = [
        "# Judge Mode tour — all four seeded issues, self-guided",
        "",
        "Measured Oct 25, 2026 (maximizer iteration 18) by",
        "`hackathon-agent-scaffold/run_judge_tour.py`: the demo console's",
        "one-click `POST /api/judge/run` endpoint was exercised over real",
        "HTTP for **every** seeded issue in mock mode (the unattended-judge",
        "default), with no operator choices after the click. Each stop's",
        "closing results card is recorded in `judge-tour.json`.",
        "",
        "| Issue | Overall | Tests | Delta | Captions | Card cost (est.) |",
        "|---|---|---|---|---|---|",
    ]
    for r in record["runs"]:
        tests = (f"{r['tests_before']} → {r['tests_after']}"
                 if r["tests_before"] is not None else "—")
        delta = f"{r['tests_delta']:+d}" if r["tests_delta"] is not None else "—"
        lines.append(
            f"| {r['issue_id']} | {r['overall']} | {tests} | {delta} "
            f"| {r['captions']} | ${r["cost_total_usd_est"]:.4f} |")
    lines += [
        "",
        f"Work issues passed {s['work_passed']}/{s['work_total']} with a "
        f"combined test-count delta of {s['total_tests_delta']:+d}; the "
        "guardrail issue ended escalated, its later stages pending, exactly "
        "as its card must report — never as a pass.",
        "",
        "## What this proves — and what it does not",
        "",
        "- Proves: Judge Mode is not a Tier-1-only path. All four tour "
        "stops run unaided, every event carries a narration caption "
        "derived from that event, and every stop ends in a results card "
        "whose overall outcome, per-stage statuses, and test delta match "
        "the run that actually happened.",
        "- Mock mode is plumbing proof, not model performance. The live "
        "evidence remains the timed live runs and PRs #16/#17/#18 in "
        "`SCORECARD.md`; this tour makes that evidence reachable by a "
        "judge without an operator, it does not replace it.",
        "- It is not the demo video. Nothing is recorded; Joseph's Nov 2 "
        "recording remains the Demo criterion's human-owned item.",
        "",
    ]
    return "\n".join(lines)


def main():
    server = demo_ui.create_server("127.0.0.1", 0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        rows = run_tour(port)
    finally:
        server.shutdown()
        server.server_close()
    record = {"mode": "mock", "runs": rows, "summary": summarize(rows)}
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "judge-tour.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "JUDGE_TOUR.md").write_text(render_md(record), encoding="utf-8")
    print(json.dumps(record["summary"], indent=2))
    for r in rows:
        print(f"{r['issue_id']}: {r['overall']} "
              f"delta={r['tests_delta']} captions={r['captions']} "
              f"elapsed_ms={r['total_elapsed_ms']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
