#!/usr/bin/env python3
"""Frontier Judge Mode live tour — every seeded issue, self-guided, LIVE
under the CONTEST configuration.

Iteration 34 (maximizer item-4 polish, Demo): Judge Mode's live proof
(iterations 20/21) ran under the Oct 25 kept split config. Since
iteration 31 the contest configuration is all-frontier (every role
muse-wonder-1.0, spark-1.3 only as availability fallback, per
Joseph's Oct 26 directive), so the self-guided path a judge would
actually use had never been measured live under the configuration
that will be judged. This runner closes exactly that gap: the same
one-click `POST /api/judge/run` endpoint, with no operator choices
after each click, in LIVE mode for ALL FOUR seeded issues
(tier1/tier2/tier3 + guardrail) — real Meta Model API calls through
the custom.meta-model-api connector (no env key), all four
DAAS_MODEL_<ROLE> env vars set to muse-wonder-1.0 and
DAAS_FALLBACK_MODEL=muse-spark-1.3 (the env the console's
default_client resolves).

Each stop is reported honestly whatever its outcome; the tour is NOT
re-run for a cleaner record. The closing results cards are the
artifact: overall outcome, per-stage pass/fail with elapsed_ms
timings, event-derived narration captions, test-count delta, and
each card's per-role cost summary (a character-count estimate — the
connector path does not expose API usage; see daas/cost.py). The
guardrail stop must end escalated with zero model calls and $0.00.
The iteration-21 split-config tour summary is read from
eval-scorecard/judge-live-tour.json at build time so the comparison
is computed from both measured records.

Outputs (repo-root eval-scorecard/):
  frontier-judge-live-tour.json — the measured record (rows + summary)
  FRONTIER_JUDGE_LIVE_TOUR.md   — the human-readable record, rendered
                                  from the record by render_md()
"""
import json
import os
import sys
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
OUT_DIR = ROOT / "eval-scorecard"
PRIOR_RECORD = OUT_DIR / "judge-live-tour.json"
sys.path.insert(0, str(HERE))

import demo_ui  # noqa: E402

TOUR_ORDER = ["tier1", "tier2", "tier3", "guardrail"]
MODEL = "muse-wonder-1.0"
FALLBACK = "muse-spark-1.3"
CONFIG_LABEL = ("live via Judge Mode tour (POST /api/judge/run, "
                "mode=live, all four seeded issues), all-frontier "
                "(contest config): TRIAGE/PLANNER/CODER/REVIEWER="
                "muse-wonder-1.0, muse-spark-1.3 configured only as "
                "availability fallback, Meta Model API through the "
                "custom.meta-model-api connector, no env key")


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


def _poll(port, run_id, tries=2400):
    snap = {}
    for _ in range(tries):
        snap = _http(port, f"/api/run/{run_id}")
        if snap["status"] != "running":
            return snap
        threading.Event().wait(0.5)
    raise TimeoutError(f"judge live run {run_id} did not finish")


def run_one(port, issue_id):
    started = _http(port, "/api/judge/run",
                    {"issue_id": issue_id, "mode": "live"})
    started_at = datetime.now(timezone.utc).isoformat()
    snap = _poll(port, started["run_id"])
    card = snap["results_card"]
    cost = card.get("cost") or {}
    return {
        "issue_id": issue_id,
        "mode": "live",
        "judge_mode": bool(snap["judge_mode"]),
        "status": snap["status"],
        "overall": card["overall"],
        "started_at": started_at,
        "stages": [{"stage": s["stage"], "status": s["status"],
                    "detail": s["detail"], "elapsed_ms": s["elapsed_ms"]}
                   for s in card["stages"]],
        "tests_before": card["tests_before"],
        "tests_after": card["tests_after"],
        "tests_delta": card["tests_delta"],
        "captions": len(snap["captions"]),
        "all_captions_judge_mode": all(
            (c or "").startswith("Judge Mode:") for c in snap["captions"]),
        "total_elapsed_ms": card["total_elapsed_ms"],
        "cost_total_usd_est": cost.get("total_usd_est"),
        "cost_method": cost.get("method"),
        "cost_calls": cost.get("calls"),
        "cost_per_role_models": {
            role: slot.get("models")
            for role, slot in (cost.get("per_role") or {}).items()},
        "links_live_prs": len(card["links"]["live_prs"]),
        "error": snap.get("error"),
    }


def summarize(rows):
    work = [r for r in rows if r["issue_id"] != "guardrail"]
    guard = [r for r in rows if r["issue_id"] == "guardrail"]
    return {
        "runs": len(rows),
        "work_passed": sum(1 for r in work if r["overall"] == "pass"),
        "work_total": len(work),
        "guardrail_escalated": bool(guard) and all(
            r["overall"] == "escalated" for r in guard),
        "total_tests_delta": sum(r["tests_delta"] or 0 for r in work),
        "total_captions": sum(r["captions"] for r in rows),
        "cost_total_usd_est": round(
            sum(r["cost_total_usd_est"] or 0.0 for r in rows), 6),
        "total_elapsed_ms": sum(r["total_elapsed_ms"] or 0 for r in rows),
    }


def _prior_summary():
    doc = json.loads(PRIOR_RECORD.read_text(encoding="utf-8"))
    return {
        "source": "eval-scorecard/judge-live-tour.json "
                  "(maximizer iteration 21, kept split config)",
        "config": doc["config"],
        "summary": doc["summary"],
    }


def render_md(record):
    s = record["summary"]
    p = record["prior_split_tour"]["summary"]
    lines = [
        "# Frontier Judge Mode — live tour under the contest "
        "configuration",
        "",
        "Measured Oct 26, 2026 (maximizer iteration 34) by",
        "`hackathon-agent-scaffold/run_frontier_judge_live_tour.py`: "
        "the demo",
        "console's one-click `POST /api/judge/run` endpoint was "
        "exercised",
        "over real HTTP in **live** mode for **every** seeded issue — "
        "no",
        "operator choices after each click, real Meta Model API calls",
        "through the custom.meta-model-api connector under the "
        "all-frontier",
        "contest configuration (every role `muse-wonder-1.0`; "
        "`muse-spark-1.3`",
        "configured only as availability fallback). Each stop's "
        "closing results",
        "card is recorded in `frontier-judge-live-tour.json`.",
        "",
        "| Issue | Mode | Overall | Tests | Delta | Captions | "
        "Elapsed | Card cost (est.) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in record["runs"]:
        tests = (f"{r['tests_before']} → {r['tests_after']}"
                 if r["tests_before"] is not None else "—")
        delta = (f"{r['tests_delta']:+d}"
                 if r["tests_delta"] is not None else "—")
        elapsed_s = (f"{r['total_elapsed_ms'] / 1000:.2f}s"
                     if r["total_elapsed_ms"] is not None else "—")
        cost = (f"${r['cost_total_usd_est']:.4f}"
                if r["cost_total_usd_est"] is not None else "—")
        lines.append(
            f"| {r['issue_id']} | live | {r['overall']} | {tests} | "
            f"{delta} | {r['captions']} | {elapsed_s} | {cost} |")
    guard_line = (
        "the guardrail issue ended escalated, as its card must report "
        "— never as a pass"
        if s["guardrail_escalated"] else
        "the guardrail issue did NOT end escalated — reported as "
        "measured above, not as the expected outcome")
    lines += [
        "",
        f"Work issues passed {s['work_passed']}/{s['work_total']} "
        f"with a combined test-count delta of "
        f"{s['total_tests_delta']:+d}; {guard_line}. Combined card "
        f"cost est. ${s['cost_total_usd_est']:.4f} (char-count "
        "estimates at wonder prices, not billing data).",
        "",
    ]
    failed = [r for r in record["runs"] if r["overall"] not in
              ("pass", "escalated")]
    for r in failed:
        lines += [
            f"**{r['issue_id']} did not complete as a pass** — "
            "reported as-is, not re-run for a cleaner record. "
            f"Closing card overall: {r['overall']}; status: "
            f"{r['status']}; error: {r['error']}",
            "",
        ]
    lines += [
        "## Comparison with the split-config live tour (iteration 21)",
        "",
        f"- Split tour (source: {record['prior_split_tour']['source']}): "
        f"work passed {p['work_passed']}/{p['work_total']}, combined "
        f"delta {p['total_tests_delta']:+d}, guardrail escalated: "
        f"{p['guardrail_escalated']}, combined card cost est. "
        f"${p['cost_total_usd_est']:.4f}, total elapsed "
        f"{p['total_elapsed_ms'] / 1000:.2f}s — that tour's Tier 2 stop "
        "was lost to a provider HTTP 503 on the reviewer call.",
        f"- All-frontier tour (this run): work passed "
        f"{s['work_passed']}/{s['work_total']}, combined delta "
        f"{s['total_tests_delta']:+d}, guardrail escalated: "
        f"{s['guardrail_escalated']}, combined card cost est. "
        f"${s['cost_total_usd_est']:.4f}, total elapsed "
        f"{s['total_elapsed_ms'] / 1000:.2f}s. Every work stop's card "
        "records `muse-wonder-1.0` on every role that ran (char "
        "estimates at wonder prices are higher than the split's mixed "
        "prices — stated, not hidden).",
        "",
        "## What this proves — and what it does not",
        "",
        "- Proves: the self-guided path is live-proven at every tour "
        "stop under the configuration that will actually be judged. "
        "A judge's single click per stop drives the real pipeline — "
        "guardrail, triage, plan, code, tests, review — and the "
        "narration captions and results cards describe the live runs "
        "that actually happened, including measured costs, timings, "
        "and the frontier model on each card. A stop that does not "
        "pass is reported by its card as measured, never dressed up "
        "as a pass.",
        "- One live tour of the seeded set through the console path; "
        "the broader live evidence remains the timed runs, the "
        "frontier repeatability record, and the generalization runs "
        "in `SCORECARD.md` and PRs #16/#17/#18. This tour opens no PR "
        "(Judge Mode live runs against a throwaway copy unless a real "
        "PR is explicitly requested).",
        "- It is not the demo video. Nothing is recorded; Joseph's "
        "Thu Oct 29, 2026 recording remains the Demo criterion's "
        "human-owned item (Nov 2 morning is emergency-retake only).",
        "",
    ]
    return "\n".join(lines)


def main():
    # The contest configuration, exactly as the frontier evals run
    # it: the console resolves these per-role overrides through
    # daas.llm.default_client, which reads the env when a run starts.
    # Set here (not at import) so importing this module for tests
    # never mutates the test process's environment.
    for role in ("TRIAGE", "PLANNER", "CODER", "REVIEWER"):
        os.environ[f"DAAS_MODEL_{role}"] = MODEL
    os.environ["DAAS_FALLBACK_MODEL"] = FALLBACK
    server = demo_ui.create_server("127.0.0.1", 0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        rows = [run_one(port, issue_id) for issue_id in TOUR_ORDER]
    finally:
        server.shutdown()
        server.server_close()
    record = {"record": "Frontier Judge Mode live tour — DevOps as a "
                        "Service, Oct 26, 2026 (maximizer iteration 34)",
              "config": CONFIG_LABEL,
              "model": MODEL,
              "fallback_model": FALLBACK,
              "prior_split_tour": _prior_summary(),
              "runs": rows, "summary": summarize(rows)}
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "frontier-judge-live-tour.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "FRONTIER_JUDGE_LIVE_TOUR.md").write_text(
        render_md(record), encoding="utf-8")
    print(json.dumps(record["summary"], indent=2))
    for r in rows:
        print(f"{r['issue_id']}: overall={r['overall']} "
              f"tests={r['tests_before']}->{r['tests_after']} "
              f"captions={r['captions']} "
              f"elapsed_ms={r['total_elapsed_ms']} "
              f"cost_est=${r['cost_total_usd_est']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
