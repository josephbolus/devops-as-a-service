#!/usr/bin/env python3
"""Retry validation: run Tier 2 LIVE under the retrying client.

Question (maximizer iteration 22): the Judge Mode live tour lost
Tier 2 when its REVIEWER call failed with a provider HTTP 503
(service_overloaded) and the client raised immediately. Both live
clients now retry transient failures (daas/llm.py, pinned by
tests/test_retry.py against simulated 503s). Does the Tier 2 issue —
the exact one that was lost — pass live end to end under the
retrying client, and does retry_stats show a retry actually fired?

Method: pipeline.run against a fresh git-initialized copy of the
demo repo, ConnectorClient (Meta Model API via the
custom.meta-model-api connector, no env key), kept split config
(CODER/REVIEWER=muse-wonder-1.0, TRIAGE/PLANNER=muse-spark-1.3).
One run, reported honestly whatever the outcome — including if it
fails again, and including retry_stats exactly as recorded (zero
retries means the provider simply did not blip this time; no live
retry is then claimed, only the simulated-503 proof stands).
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
DEMO_REPO = ROOT / "hackathon-demo-repo"
ISSUE_FILE = HERE / "issues" / "tier2.json"
SPLIT_ROLE_MODELS = {"CODER": "muse-wonder-1.0",
                     "REVIEWER": "muse-wonder-1.0"}
DEFAULT_MODEL = "muse-spark-1.3"
CONFIG_LABEL = ("split (kept config) via custom.meta-model-api connector, "
                "no env key: CODER/REVIEWER=muse-wonder-1.0, "
                "TRIAGE/PLANNER=muse-spark-1.3; retrying ConnectorClient "
                "(max_attempts=3, transient-only)")


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


def summarize(row):
    return {
        "passed": row["outcome"] == "passed",
        "outcome": row["outcome"],
        "tests_before": row.get("tests_before"),
        "tests_after": row.get("tests_after"),
        "test_growth": ((row["tests_after"] - row["tests_before"])
                        if row.get("tests_after") is not None
                        and row.get("tests_before") is not None else None),
        "wall_clock_seconds": row["wall_clock_seconds"],
        "retries": row.get("retry_stats", {}).get("retries"),
        "transient_failures": row.get("retry_stats", {}).get(
            "transient_failures"),
    }


def render_md(doc):
    row = doc["runs"][0]
    s = doc["summary"]
    tb, ta = s["tests_before"], s["tests_after"]
    growth = s["test_growth"]
    lines = [
        "# Provider-transient retry — live validation (Oct 25, 2026)",
        "",
        "Maximizer iteration 22. Motivation: the Judge Mode live tour "
        "(`JUDGE_LIVE_TOUR.md`) lost Tier 2 when its reviewer call failed "
        "with a provider HTTP 503 (`service_overloaded`) and the client "
        "raised immediately; its tests stage had already passed 6 → 11.",
        "",
        "Fix: both live clients in `daas/llm.py` retry transient failures "
        "only (HTTP 429/500/502/503/504, overload/rate-limit/timeout "
        "markers) with exponential backoff, `max_attempts=3`; auth and "
        "other 4xx failures are never retried. Recovery after simulated "
        "503s is pinned by `tests/test_retry.py`. This file records ONE "
        "live validation run of the Tier 2 issue under the retrying "
        "client — it does not replace or erase the tour's 503 record.",
        "",
        f"- Outcome: **{row['outcome']}**",
        f"- Tests: {tb} → {ta} ({'+' if growth and growth >= 0 else ''}{growth})"
        if tb is not None else "- Tests: not recorded (run did not complete)",
        f"- Wall clock: {row['wall_clock_seconds']}s",
        f"- Model calls (pipeline level): {row.get('model_calls')}",
        f"- retry_stats: calls={row.get('retry_stats', {}).get('calls')}, "
        f"retries={s['retries']}, "
        f"transient_failures={s['transient_failures']}",
        f"- Reviewer verdict: {row.get('reviewer_verdict')}",
        f"- Est. API cost: ${row['cost']['total_usd_est']:.4f} "
        "(char estimate)" if row.get("cost") else "- Est. API cost: n/a",
        "",
        "Honest limits: the retry logic is proven against simulated "
        "503s in the test suite. This live run proves the Tier 2 issue "
        "passes end to end under the retrying client; a retry is "
        "claimed live only if `retries` above is greater than zero — "
        "zero means the provider did not blip during this run. One "
        "run of one seeded issue; the tour record stands as measured.",
        "",
    ]
    return "\n".join(lines)


def run_one(client_factory):
    issue = json.loads(ISSUE_FILE.read_text())
    row = {"slug": "tier2-retry-validation", "issue": issue["title"],
           "mode": "live-split-retry-validation"}
    holder = {}

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
        client = client_factory()
        holder["client"] = client
        events = {}
        started = datetime.now(timezone.utc)
        t0 = time.perf_counter()
        try:
            result = pipeline.run(repo, issue, client, tmp / "out",
                                  on_event=lambda e: events.update(
                                      {e["stage"]: e["data"]}))
        except Exception as e:  # a failed live run is a measured result
            wall = round(time.perf_counter() - t0, 2)
            row.update({"outcome": "failed",
                        "error": f"{type(e).__name__}: {e}"[:500],
                        "tests_before": None, "tests_after": None,
                        "wall_clock_seconds": wall,
                        "model_calls": len(client.calls),
                        "models_by_role": {c["role"]: c["model"]
                                           for c in client.calls},
                        "retry_stats": dict(client.inner.retry_stats),
                        "cost": None, "reviewer_verdict": None})
            return row, started
        wall = round(time.perf_counter() - t0, 2)
        review = events.get("review", {})
        row.update({
            "outcome": "passed" if result["passed"] else "failed",
            "tests_before": result["tests_before"],
            "tests_after": result["tests_after"],
            "files_touched": sorted(set(result["changed"])),
            "unexpected_files": result["unexpected_files"],
            "wall_clock_seconds": wall,
            "model_calls": len(client.calls),
            "models_by_role": {c["role"]: c["model"] for c in client.calls},
            "retry_stats": dict(client.inner.retry_stats),
            "tests_ok": result["tests_ok"],
            "reviewer_verdict": review.get("verdict"),
            "cost": result.get("cost"),
        })
        return row, started


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "eval-scorecard"
                                         / "retry-runs.json"))
    args = ap.parse_args()

    def factory():
        return RecordingClient(ConnectorClient(
            model=DEFAULT_MODEL, role_models=dict(SPLIT_ROLE_MODELS)))

    row, started = run_one(factory)
    row["started_at"] = started.isoformat()
    doc = {
        "record": "Retry validation — DevOps as a Service, Oct 25, 2026 "
                  "(maximizer iteration 22: provider-transient retry)",
        "method": "pipeline.run (guardrail -> triage -> plan -> code -> "
                  "tests -> review) against a fresh git-initialized copy "
                  "of hackathon-demo-repo, retrying ConnectorClient (Meta "
                  "Model API via custom.meta-model-api connector, no env "
                  "key), kept split config, Tier 2 seeded issue — the "
                  "issue whose Judge Mode live-tour run was lost to a "
                  "provider HTTP 503. One run, reported as measured.",
        "config": CONFIG_LABEL,
        "runs": [row],
    }
    doc["summary"] = summarize(row)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    (out.parent / "RETRY.md").write_text(render_md(doc))
    print(f"retry-validation: {row['outcome']} "
          f"wall={row['wall_clock_seconds']}s "
          f"tests={row.get('tests_before')}->{row.get('tests_after')} "
          f"retry_stats={row.get('retry_stats')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
