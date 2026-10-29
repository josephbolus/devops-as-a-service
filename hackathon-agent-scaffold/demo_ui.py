#!/usr/bin/env python3
"""Demo console for DevOps as a Service — a local web UI over the pipeline.

Launch:
  python3 demo_ui.py [--port 8765] [--host 127.0.0.1]

Open http://127.0.0.1:8765/ — pick an issue, pick Mock (offline
MockClient, deterministic) or Live (real Meta Model API through
daas.llm.default_client, i.e. the connector path), and watch the
stages fill in: guardrail -> triage -> plan -> code -> tests ->
review -> done. Runs execute against a fresh throwaway copy of
../hackathon-demo-repo (git-initialized so diffs render); the pristine
demo repo is never mutated — EXCEPT Live + "Open real PR", which
drives run_pr.run against the real demo repo and opens a real PR.

The "Try to break it" panel posts arbitrary text to the deterministic
guardrail; escalations come back with the human-approval handoff
(daas/approval.py) rendered for display.

Stdlib only: http.server + threading + json. No credentials are read,
accepted, or logged here — live mode goes through default_client(),
which resolves the connector credential outside this process.

The v3 console (approved redesign, light + dark themes) is served at
/v3 and consumes the same JSON API as the classic page at / — plus one
read-only addition, GET /api/meta, which feeds its header KPI strip
from the eval-scorecard artifacts. The classic page is unchanged.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import run_pr  # noqa: E402
from daas import approval, guardrail, pipeline  # noqa: E402
from daas import cost as daas_cost  # noqa: E402
from daas.llm import default_client  # noqa: E402

HERE = Path(__file__).parent
DEMO_REPO = (HERE.parent / "hackathon-demo-repo").resolve()
ISSUES_DIR = HERE / "issues"

# (issue file stem, display label, one-line blurb)
# The 9 expansion issues (iterations 35-37) are LIVE-only in the console:
# MockClient has no canned answers for them, so a mock run of an
# expansion issue is not model evidence and its card will report the
# mock attempt as measured (it cannot pass with a Tier-1 canned fix).
ISSUE_CATALOG = [
    ("tier1", "Tier 1 — Bug fix", "paginate() returns one item short on full pages."),
    ("tier2", "Tier 2 — Feature", "Add retry with backoff to the HTTP client wrapper."),
    ("tier3", "Tier 3 — Feature", "Make the CLI output machine-readable (--json)."),
    ("config_drift", "Expansion — Config drift (live only)", "load_config() silently ignores APP_* environment overrides."),
    ("health_check", "Expansion — Health check (live only)", "overall_status() reports healthy while a critical check is down."),
    ("alert_threshold", "Expansion — Alert threshold (live only)", "should_page() comparison is inverted: pages on healthy values."),
    ("connection_pool", "Expansion — Connection pool (live only)", "ConnectionPool.run() leaks connections on the error path."),
    ("log_rotation", "Expansion — Log rotation (live only)", "LogWriter never rotates and fills the disk."),
    ("scheduled_job", "Expansion — Scheduled job (live only)", "run_once() silently skips after a transient failure."),
    ("retry_storm", "Expansion — Retry storm (live only)", "call_with_retry() never sleeps between retries."),
    ("deploy_token", "Expansion — Deploy token (live only)", "run_deploy() crashes on an expired token and prints the token."),
    ("api_pagination", "Expansion — API pagination (live only)", "fetch_all() silently drops every page after the first."),
    ("guardrail", "Guardrail — Destructive", "Delete the legacy database and drop old tables. Must escalate."),
]


def issue_catalog():
    """The seeded issues, with titles/bodies read from issues/*.json."""
    out = []
    for stem, label, blurb in ISSUE_CATALOG:
        issue = json.loads((ISSUES_DIR / f"{stem}.json").read_text())
        out.append({"id": stem, "label": label, "blurb": blurb,
                    "title": issue["title"], "body": issue.get("body", ""),
                    "kind": "guardrail" if stem == "guardrail" else "work"})
    return out


def load_issue(issue_id):
    for entry in issue_catalog():
        if entry["id"] == issue_id:
            return {"title": entry["title"], "body": entry["body"]}
    return None


# ---------------------------------------------------------------- judge mode

REPO_URL = "https://github.com/josephbolus/devops-as-a-service"
EVAL_SCORECARD_URL = REPO_URL + "/blob/main/eval-scorecard/SCORECARD.md"
GENERALIZATION_URL = REPO_URL + "/blob/main/eval-scorecard/GENERALIZATION.md"
LIVE_PR_URLS = [REPO_URL + "/pull/16", REPO_URL + "/pull/17",
                REPO_URL + "/pull/18"]
JUDGE_STAGES = ["guardrail", "triage", "plan", "code", "tests", "review", "done"]


def caption_for_event(event):
    """Narration caption for one pipeline event — Judge Mode speaks in
    plain language about what just happened and why it matters, tied to
    the event that actually fired (never pre-scripted stage text)."""
    stage, d = event.get("stage"), event.get("data") or {}
    if stage == "guardrail":
        if d.get("blocked"):
            return ("Judge Mode: Stop — the deterministic guardrail blocked this "
                    "request before any model ran. Nothing was changed; a human "
                    "receives the approval request instead. That is the safety "
                    "story of this system, in one event.")
        return ("Judge Mode: First, a deterministic guardrail — plain code, not "
                "a model — checked this issue for destructive requests. It "
                "passed, so the agents may proceed.")
    if stage == "triage":
        return (f"Judge Mode: The triage agent classified this as a "
                f"{d.get('kind', 'issue')} and wrote the acceptance criteria "
                f"the rest of the pipeline will be judged against.")
    if stage == "plan":
        steps = d.get("steps") or []
        return (f"Judge Mode: The planner read the repository tree and laid "
                f"out {len(steps)} step(s), naming the exact files it expects "
                f"to change. Anything outside that list fails the run.")
    if stage == "code":
        changed = d.get("changed") or []
        return (f"Judge Mode: The coder edited {len(changed)} file(s) — "
                f"{', '.join(changed) or 'none'} — including a new regression "
                f"test, following the plan rather than improvising.")
    if stage == "tests":
        delta = (d.get("tests_after") or 0) - (d.get("tests_before") or 0)
        verdict = "passed" if d.get("tests_ok") else "FAILED"
        return (f"Judge Mode: The full test suite ran and {verdict}: "
                f"{d.get('tests_before')} → {d.get('tests_after')} discovered "
                f"tests ({delta:+d}). A new test only counts if the count grows.")
    if stage == "regression_gate":
        if not d.get("applicable"):
            return ("Judge Mode: A deterministic regression gate checked "
                    "whether the new tests fail on the original code; it "
                    "was not applicable to this change shape.")
        verdict = "failed on the original code, as a real regression test must" \
            if d.get("passed") else \
            "PASSED on the original code too — so they prove nothing, and this run cannot pass"
        return (f"Judge Mode: A deterministic regression gate — plain code, "
                f"not a model — re-ran the new tests against the original "
                f"production code. The suite {verdict}.")
    if stage == "target_gate":
        if not d.get("applicable"):
            return ("Judge Mode: A deterministic issue-target gate checked "
                    "whether the fix touches the function the issue actually "
                    "names; it was not applicable to this issue.")
        verdict = ("changes the function the issue names"
                   if d.get("passed") else
                   "does NOT touch the function the issue names — an "
                   "off-target fix, however real, cannot pass this run")
        return (f"Judge Mode: A deterministic issue-target gate — plain "
                f"code, not a model — verified the production change "
                f"{verdict}.")
    if stage == "review":
        return (f"Judge Mode: An independent reviewer agent read the actual "
                f"diff and returned '{d.get('verdict', '?')}'. The pipeline "
                f"only calls a run PR-ready when the reviewer approves.")
    if stage == "done":
        r = d.get("result") or {}
        if r.get("passed"):
            return ("Judge Mode: Done — every stage passed, so this run is "
                    "PR-ready. The results card below collects the evidence.")
        return ("Judge Mode: Done — this run is NOT PR-ready. The results "
                "card below shows exactly which stage held it back.")
    if stage == "resume":
        return (f"Judge Mode: A human recorded a '{d.get('decision')}' "
                f"decision; the pipeline resumes only on that instruction.")
    return f"Judge Mode: Stage '{stage}' fired."


def results_card(snapshot):
    """Closing Judge Mode results card, derived only from a run
    snapshot's real events/result: pass/fail per stage, per-stage
    timing (elapsed_ms recorded when the event fired), the test-count
    delta, and links to the opened PRs and the eval scorecard."""
    events = snapshot.get("events") or []
    by_stage = {}
    for e in events:
        by_stage.setdefault(e.get("stage"), e)
    result = snapshot.get("result") or {}
    if not result and "done" in by_stage:
        result = (by_stage["done"].get("data") or {}).get("result") or {}
    stages = []
    for stage in JUDGE_STAGES:
        e = by_stage.get(stage)
        entry = {"stage": stage, "status": "pending", "detail": "",
                 "elapsed_ms": e.get("elapsed_ms") if e else None}
        if e is not None:
            d = e.get("data") or {}
            if stage == "guardrail":
                entry["status"] = "escalated" if d.get("blocked") else "pass"
                entry["detail"] = d.get("reason", "") if d.get("blocked") else "allowed"
            elif stage == "tests":
                entry["status"] = "pass" if d.get("tests_ok") else "fail"
                entry["detail"] = (f"{d.get('tests_before')} → {d.get('tests_after')} "
                                   f"({(d.get('tests_after') or 0) - (d.get('tests_before') or 0):+d})")
            elif stage == "review":
                entry["status"] = "pass" if d.get("verdict") == "approve" else "fail"
                entry["detail"] = d.get("verdict", "")
            elif stage == "done":
                entry["status"] = "pass" if result.get("passed") else "fail"
                entry["detail"] = "PR-ready" if result.get("passed") else "not PR-ready"
            else:
                entry["status"] = "pass"
                entry["detail"] = "completed"
        stages.append(entry)
    tests_ev = by_stage.get("tests", {}).get("data") or {}
    pr_url = result.get("pr_url")
    return {
        "status": snapshot.get("status"),
        "overall": ("escalated" if snapshot.get("status") == "escalated"
                    else "pass" if result.get("passed") else
                    "fail" if snapshot.get("status") in ("done", "error") else "running"),
        "stages": stages,
        "tests_before": tests_ev.get("tests_before", result.get("tests_before")),
        "tests_after": tests_ev.get("tests_after", result.get("tests_after")),
        "tests_delta": ((tests_ev.get("tests_after") - tests_ev.get("tests_before"))
                        if tests_ev.get("tests_after") is not None
                        and tests_ev.get("tests_before") is not None else None),
        "total_elapsed_ms": (events[-1].get("elapsed_ms") if events else None),
        "cost": (result.get("cost") if result.get("cost") else
                 daas_cost.summarize([]) if snapshot.get("status") == "escalated"
                 else None),
        "pr_url": pr_url,
        "links": {"pr_url": pr_url, "live_prs": list(LIVE_PR_URLS),
                  "eval_scorecard": EVAL_SCORECARD_URL,
                  "generalization": GENERALIZATION_URL,
                  "repository": REPO_URL},
    }


# ---------------------------------------------------------------- meta

SCORECARD_DIR = HERE.parent / "eval-scorecard"
# The maximizer's weighted internal score: the criterion means weighted
# by the judging weights (Impact 95 x .30, Tooling 92 x .25, Demo 87 x
# .25, Depth 97 x .20 = 92.65; hackathon-maximizer scorecard, Oct 28).
# It is not an eval-scorecard artifact, so it lives here as a cited
# constant; every other KPI below is read from the artifacts.
WEIGHTED_SCORECARD_SCORE = 92.65


def meta_kpis():
    """Header KPI strip for the v3 console, read from the measured
    eval-scorecard artifacts (the frontier full-bench record) plus the
    live PR links this module already publishes. Read-only."""
    bench = json.loads(
        (SCORECARD_DIR / "frontier-full-bench-runs.json").read_text())
    summary = bench["summary"]
    passed_s, total_s = str(summary["work_issues_passed"]).split("/")
    cost = round(float(summary["cost_per_passed_issue"]), 4)
    return {
        "scenarios": {"passed": int(passed_s), "total": int(total_s),
                      "display": str(summary["work_issues_passed"])},
        "net_new_tests": int(summary["test_growth"]),
        "est_cost_per_issue_usd": cost,
        "est_cost_per_issue_display": f"{cost * 100:.1f}¢",
        "live_prs": list(LIVE_PR_URLS),
        "live_prs_count": len(LIVE_PR_URLS),
        "weighted_score": WEIGHTED_SCORECARD_SCORE,
        "bench_wall_clock_seconds": summary["total_wall_clock_seconds"],
    }


# ---------------------------------------------------------------- runs

_RUNS = {}
_RUNS_LOCK = threading.Lock()


def _new_run(issue_id, mode, open_pr, judge_mode=False):
    run_id = uuid.uuid4().hex[:12]
    record = {"id": run_id, "issue_id": issue_id, "mode": mode,
              "open_pr": open_pr, "judge_mode": bool(judge_mode),
              "status": "running", "events": [],
              "result": None, "error": None, "lock": threading.Lock(),
              "started": time.monotonic()}
    with _RUNS_LOCK:
        _RUNS[run_id] = record
    return record


def get_run(run_id):
    with _RUNS_LOCK:
        return _RUNS.get(run_id)


def _collector(record):
    def collect(event):
        event = dict(event)
        event["elapsed_ms"] = int((time.monotonic() - record["started"]) * 1000)
        event["caption"] = caption_for_event(event)
        with record["lock"]:
            record["events"].append(event)
    return collect


def _git(work, *args):
    subprocess.run(["git", "-C", str(work), *args],
                   capture_output=True, text=True, check=False)


def _execute_run(record):
    issue = load_issue(record["issue_id"])
    collect = _collector(record)
    sandbox = Path(tempfile.mkdtemp(prefix="daas-ui-"))
    out_dir = sandbox / "out"
    try:
        if record["mode"] == "live" and record["open_pr"]:
            outcome = run_pr.run(DEMO_REPO, issue, out_dir, base="main",
                                 mock=False, on_event=collect)
            result = outcome["result"]
            if result is not None:
                result = dict(result, pr_url=outcome["pr_url"])
                body_path = out_dir / "pr_body.md"
                if body_path.exists():
                    result["pr_body"] = body_path.read_text()
                record["result"] = result
            if outcome["exit"] == 2:
                record["status"] = "escalated"
            elif outcome["exit"] == 0:
                record["status"] = "done"
            elif outcome["exit"] == 3:
                record["status"] = "error"
                record["error"] = "Target repo has uncommitted changes; PR run aborted."
            else:
                record["status"] = "done"  # ran, but not PR-ready
            return

        work = sandbox / "repo"
        shutil.copytree(DEMO_REPO, work,
                        ignore=shutil.ignore_patterns("__pycache__"))
        # Give the copy its own git history so the code stage's diff
        # renders tracked-file changes, not just new files.
        _git(work, "init", "-q")
        _git(work, "add", "-A")
        _git(work, "-c", "user.name=daas-demo", "-c",
             "user.email=daas-demo@localhost", "commit", "-qm", "baseline")

        client = default_client(mock=(record["mode"] == "mock"))
        try:
            result = pipeline.run(work, issue, client, out_dir,
                                  on_event=collect)
        except pipeline.Escalation:
            record["status"] = "escalated"
            return
        body_path = out_dir / "pr_body.md"
        if body_path.exists():
            result = dict(result, pr_body=body_path.read_text())
        record["result"] = result
        record["status"] = "done"
    except Exception as e:  # surfaced to the UI, never swallowed
        record["status"] = "error"
        record["error"] = f"{type(e).__name__}: {e}"


def start_run(issue_id, mode, open_pr, judge_mode=False):
    record = _new_run(issue_id, mode, open_pr, judge_mode=judge_mode)
    threading.Thread(target=_execute_run, args=(record,), daemon=True).start()
    return record


def start_judge_run(issue_id="tier1", mode="mock"):
    """One-click Judge Mode: a self-guided run a judge can start with no
    operator choices — defaults to the Tier 1 issue in mock mode (offline,
    deterministic) unless the caller names another seeded issue/mode."""
    if load_issue(issue_id) is None:
        raise ValueError(f"unknown issue_id {issue_id!r}")
    if mode not in ("mock", "live"):
        raise ValueError("mode must be 'mock' or 'live'")
    return start_run(issue_id, mode, False, judge_mode=True)


def run_snapshot(record):
    with record["lock"]:
        events = list(record["events"])
    snap = {"id": record["id"], "status": record["status"],
            "issue_id": record["issue_id"], "mode": record["mode"],
            "open_pr": record["open_pr"],
            "judge_mode": record.get("judge_mode", False),
            "events": events,
            "captions": [e.get("caption") for e in events],
            "result": record["result"], "error": record["error"]}
    snap["results_card"] = results_card(snap)
    return snap


def decide_approval(request, decision, decided_by, decided_at,
                    notes=None, rescoped_issue=None):
    """Record a human decision on an escalation handoff (console wiring
    for approve-and-resume). Pure validation/recording via
    daas.approval.record_decision; the actual resume runs through
    pipeline.resume / run_resume.py. Returns the decided request plus
    whether it is resumable."""
    decided = approval.record_decision(request, decision, decided_by,
                                       decided_at, notes=notes,
                                       rescoped_issue=rescoped_issue)
    return {"request": decided, "will_resume": decision == "rescope",
            "rescoped_issue": decided.get("rescoped_issue"),
            "markdown": approval.render_markdown(decided)}


def guardrail_verdict(title, body):
    """Run text through the deterministic guardrail; build the handoff
    a human would receive when it escalates."""
    blocked, reason = guardrail.check(title, body)
    if not blocked:
        return {"blocked": False}
    request = approval.build_request({"title": title, "body": body}, reason)
    return {"blocked": True, "reason": reason, "handoff": request,
            "handoff_markdown": approval.render_markdown(request)}


# ---------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    server_version = "DaasDemoUI/1.0"

    def log_message(self, *args):  # keep the console quiet
        pass

    def _send(self, code, body, content_type):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json")

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/v3":
            self._send(200, PAGE_V3, "text/html; charset=utf-8")
        elif self.path == "/api/meta":
            try:
                self._send_json(200, meta_kpis())
            except (OSError, ValueError, KeyError) as e:
                self._send_json(500, {"error": f"meta unavailable: {e}"})
        elif self.path == "/api/issues":
            self._send_json(200, {"issues": issue_catalog()})
        elif self.path.startswith("/api/run/"):
            record = get_run(self.path.rsplit("/", 1)[-1])
            if record is None:
                self._send_json(404, {"error": "unknown run id"})
            else:
                self._send_json(200, run_snapshot(record))
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        try:
            payload = self._read_json()
        except (ValueError, UnicodeDecodeError):
            self._send_json(400, {"error": "request body must be JSON"})
            return
        if self.path == "/api/judge/run":
            try:
                record = start_judge_run(str(payload.get("issue_id", "tier1")),
                                         str(payload.get("mode", "mock")))
            except ValueError as e:
                self._send_json(400, {"error": str(e)})
                return
            self._send_json(200, {"run_id": record["id"], "judge_mode": True})
        elif self.path == "/api/run":
            issue_id = payload.get("issue_id")
            mode = payload.get("mode", "mock")
            open_pr = bool(payload.get("open_pr", False))
            if load_issue(issue_id) is None:
                self._send_json(400, {"error": f"unknown issue_id {issue_id!r}"})
                return
            if mode not in ("mock", "live"):
                self._send_json(400, {"error": "mode must be 'mock' or 'live'"})
                return
            if open_pr and mode != "live":
                open_pr = False  # a real PR only makes sense live
            record = start_run(issue_id, mode, open_pr,
                               judge_mode=bool(payload.get("judge_mode", False)))
            self._send_json(200, {"run_id": record["id"]})
        elif self.path == "/api/approval/decide":
            try:
                result = decide_approval(
                    payload.get("request") or {},
                    str(payload.get("decision", "")),
                    str(payload.get("decided_by", "")),
                    str(payload.get("decided_at", "")),
                    notes=payload.get("notes"),
                    rescoped_issue=payload.get("rescoped_issue"))
            except ValueError as e:
                self._send_json(400, {"error": str(e)})
                return
            self._send_json(200, result)
        elif self.path == "/api/guardrail":
            title = str(payload.get("title", ""))
            body = str(payload.get("body", ""))
            self._send_json(200, guardrail_verdict(title, body))
        else:
            self._send_json(404, {"error": "not found"})


def create_server(host="127.0.0.1", port=8765):
    return ThreadingHTTPServer((host, port), Handler)


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DevOps as a Service — demo console</title>
<style>
  :root { --bg:#0d1117; --panel:#161b22; --panel2:#1c2330; --line:#30363d;
          --text:#e6edf3; --dim:#8b949e; --accent:#2f81f7; --green:#3fb950;
          --red:#f85149; --amber:#d29922; --mono:ui-monospace,SFMono-Regular,Menlo,monospace; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font-family:-apple-system,"Segoe UI",Helvetica,Arial,sans-serif; }
  header { padding:28px 32px 18px; border-bottom:1px solid var(--line); }
  header h1 { margin:0 0 6px; font-size:28px; }
  header p { margin:0; color:var(--dim); max-width:820px; line-height:1.45; }
  main { display:grid; grid-template-columns:360px 1fr; gap:20px; padding:20px 32px; }
  @media (max-width: 900px) { main { grid-template-columns:1fr; } }
  .panel { background:var(--panel); border:1px solid var(--line);
           border-radius:10px; padding:16px; margin-bottom:20px; }
  .panel h2 { margin:0 0 12px; font-size:15px; text-transform:uppercase;
              letter-spacing:.06em; color:var(--dim); }
  .issue { border:1px solid var(--line); border-radius:8px; padding:10px 12px;
           margin-bottom:8px; cursor:pointer; background:var(--panel2); }
  .issue:hover { border-color:var(--accent); }
  .issue.selected { border-color:var(--accent); box-shadow:0 0 0 1px var(--accent); }
  .issue .label { font-weight:600; font-size:14px; }
  .issue .title { font-size:13px; color:var(--text); margin-top:2px; }
  .issue .blurb { font-size:12px; color:var(--dim); margin-top:2px; }
  .toggle { display:flex; gap:8px; margin-bottom:12px; }
  .toggle button { flex:1; padding:8px; background:var(--panel2); color:var(--dim);
                   border:1px solid var(--line); border-radius:8px; cursor:pointer; font-size:14px; }
  .toggle button.active { color:var(--text); border-color:var(--accent);
                          box-shadow:0 0 0 1px var(--accent); }
  label.check { display:flex; gap:8px; align-items:center; font-size:14px;
                margin:10px 0; color:var(--text); }
  label.check.disabled { color:var(--dim); }
  .hint { font-size:12px; color:var(--dim); line-height:1.4; }
  #runBtn { width:100%; padding:11px; font-size:15px; font-weight:600; border:0;
            border-radius:8px; background:var(--accent); color:#fff; cursor:pointer; }
  #runBtn:disabled { opacity:.45; cursor:default; }
  #runStatus { margin-top:10px; font-size:13px; color:var(--dim); min-height:18px; }
  .stage { background:var(--panel); border:1px solid var(--line); border-radius:10px;
           padding:14px 16px; margin-bottom:12px; opacity:.38; }
  .stage.active { opacity:1; border-color:var(--accent); }
  .stage.done { opacity:1; }
  .stage h3 { margin:0 0 8px; font-size:15px; display:flex; gap:8px; align-items:center; }
  .stage .body { font-size:14px; line-height:1.5; }
  .stage .empty { color:var(--dim); font-size:13px; }
  .chip { font-size:11px; font-weight:700; padding:2px 8px; border-radius:20px;
          text-transform:uppercase; letter-spacing:.05em; }
  .chip.green { background:rgba(63,185,80,.15); color:var(--green); }
  .chip.red { background:rgba(248,81,73,.15); color:var(--red); }
  .chip.amber { background:rgba(210,153,34,.18); color:var(--amber); }
  .chip.blue { background:rgba(47,129,247,.15); color:var(--accent); }
  pre { background:#0a0e14; border:1px solid var(--line); border-radius:8px;
        padding:10px; overflow:auto; font-family:var(--mono); font-size:12px;
        line-height:1.45; white-space:pre-wrap; word-break:break-word; }
  .diff-add { color:var(--green); } .diff-del { color:var(--red); }
  ul.steps { margin:6px 0; padding-left:20px; }
  .banner { border-radius:8px; padding:12px 14px; font-weight:600; margin-bottom:10px; }
  .banner.pass { background:rgba(63,185,80,.14); color:var(--green); }
  .banner.fail { background:rgba(248,81,73,.14); color:var(--red); }
  .banner.esc { background:rgba(210,153,34,.16); color:var(--amber); }
  a { color:var(--accent); }
  textarea, input[type=text] { width:100%; background:var(--panel2); color:var(--text);
    border:1px solid var(--line); border-radius:8px; padding:9px; font-size:14px;
    font-family:inherit; margin-bottom:8px; }
  textarea { min-height:74px; resize:vertical; }
  #breakBtn { padding:9px 14px; font-weight:600; border:0; border-radius:8px;
              background:var(--amber); color:#161b22; cursor:pointer; }
  section.break { padding:0 32px 32px; }
  .cols { display:grid; grid-template-columns:360px 1fr; gap:20px; }
  @media (max-width: 900px) { .cols { grid-template-columns:1fr; } }
</style>
</head>
<body>
<header>
  <h1>DevOps as a Service</h1>
  <p>File an issue. Four agents — triage, planner, coder, reviewer — do the
     work and open the pull request. A deterministic guardrail runs before any
     model, and anything destructive escalates to a human instead.</p>
</header>
<main>
  <div>
    <div class="panel">
      <h2>Judge Mode — self-guided</h2>
      <p class="hint">One click, no operator needed: runs the Tier 1 issue
        end to end with narration captions as each stage fires, and ends
        in a results card with pass/fail per stage, timings, test-count
        deltas, and links to the live PRs and eval scorecard.</p>
      <button id="judgeBtn" style="width:100%;padding:11px;font-size:15px;font-weight:600;border:0;border-radius:8px;background:var(--green);color:#06130a;cursor:pointer;">▶ Run Judge Mode</button>
      <div id="judgeStatus" style="margin-top:10px;font-size:13px;color:var(--dim);min-height:18px;"></div>
    </div>
    <div class="panel">
      <h2>1 · Pick an issue</h2>
      <div id="issues">Loading…</div>
    </div>
    <div class="panel">
      <h2>2 · Mode</h2>
      <div class="toggle">
        <button id="modeMock" class="active">Mock (offline)</button>
        <button id="modeLive">Live (real model)</button>
      </div>
      <label class="check disabled" id="prLabel">
        <input type="checkbox" id="openPr" disabled> Open a real PR on GitHub
      </label>
      <p class="hint" id="modeHint">Mock mode runs the deterministic offline
        client against a throwaway copy of the demo repo. It proves the
        plumbing; it is not the intelligence.</p>
      <button id="runBtn">Run the agents</button>
      <div id="runStatus"></div>
    </div>
  </div>
  <div id="timeline">
    <div class="panel" id="judgeCaptionPanel" style="display:none;">
      <h2>Narration</h2>
      <div id="judgeCaption" style="font-size:15px;line-height:1.55;"></div>
    </div>
    <div class="panel" id="judgeResultsPanel" style="display:none;">
      <h2>Results card</h2>
      <div id="judgeResults"></div>
    </div>
    <div class="stage" id="stage-guardrail"><h3>🛡 Guardrail</h3><div class="body"><span class="empty">Waiting…</span></div></div>
    <div class="stage" id="stage-triage"><h3>🔍 Triage</h3><div class="body"><span class="empty">Waiting…</span></div></div>
    <div class="stage" id="stage-plan"><h3>🗺 Plan</h3><div class="body"><span class="empty">Waiting…</span></div></div>
    <div class="stage" id="stage-code"><h3>⌨️ Code</h3><div class="body"><span class="empty">Waiting…</span></div></div>
    <div class="stage" id="stage-tests"><h3>🧪 Tests</h3><div class="body"><span class="empty">Waiting…</span></div></div>
    <div class="stage" id="stage-review"><h3>👀 Review</h3><div class="body"><span class="empty">Waiting…</span></div></div>
    <div class="stage" id="stage-done"><h3>✅ Result</h3><div class="body"><span class="empty">Waiting…</span></div></div>
  </div>
</main>
<section class="break">
  <div class="cols">
    <div class="panel">
      <h2>Try to break it</h2>
      <p class="hint">The guardrail is deterministic code, not a prompt — no
        model ever sees a request it blocks. Type anything destructive and
        watch it escalate with a human-approval handoff.</p>
      <input type="text" id="breakTitle" value="Clean up the old data">
      <textarea id="breakBody">Please wipe the production database and delete all customer data so we can start fresh.</textarea>
      <button id="breakBtn">Send to the guardrail</button>
    </div>
    <div class="panel">
      <h2>Guardrail verdict</h2>
      <div id="breakResult"><span class="hint">Nothing submitted yet.</span></div>
    </div>
  </div>
</section>
<script>
const $ = id => document.getElementById(id);
let selectedIssue = null, mode = "mock", currentRun = null, rendered = 0, poller = null;

function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
}
function stageBody(stage) { return document.querySelector("#stage-" + stage + " .body"); }
function setStage(stage, fill) {
  const card = $("stage-" + stage);
  card.classList.add("active");
  const body = stageBody(stage);
  body.textContent = "";
  fill(body);
  card.classList.add("done");
  card.classList.remove("active");
}
function chip(text, kind) { return el("span", text, "chip " + kind); }

async function loadIssues() {
  const data = await (await fetch("/api/issues")).json();
  const box = $("issues"); box.textContent = "";
  data.issues.forEach(issue => {
    const card = el("div", null, "issue");
    card.appendChild(el("div", issue.label, "label"));
    card.appendChild(el("div", issue.title, "title"));
    card.appendChild(el("div", issue.blurb, "blurb"));
    card.onclick = () => {
      selectedIssue = issue.id;
      document.querySelectorAll(".issue").forEach(n => n.classList.remove("selected"));
      card.classList.add("selected");
    };
    box.appendChild(card);
    if (issue.id === "tier1") card.click();
  });
}

function setMode(m) {
  mode = m;
  $("modeMock").classList.toggle("active", m === "mock");
  $("modeLive").classList.toggle("active", m === "live");
  const live = m === "live";
  $("openPr").disabled = !live;
  $("prLabel").classList.toggle("disabled", !live);
  if (!live) $("openPr").checked = false;
  $("modeHint").textContent = live
    ? "Live mode calls the real Meta Model API (through the connector) and runs against a throwaway copy of the demo repo — unless you open a real PR, which runs against the real repo and pushes a branch."
    : "Mock mode runs the deterministic offline client against a throwaway copy of the demo repo. It proves the plumbing; it is not the intelligence.";
}
$("modeMock").onclick = () => setMode("mock");
$("modeLive").onclick = () => setMode("live");

function resetTimeline() {
  ["guardrail","triage","plan","code","tests","review","done"].forEach(s => {
    const card = $("stage-" + s);
    card.classList.remove("active", "done");
    stageBody(s).innerHTML = '<span class="empty">Waiting…</span>';
  });
  rendered = 0;
}

function renderEvent(ev) {
  const d = ev.data || {};
  if (ev.caption) {
    $("judgeCaptionPanel").style.display = "block";
    $("judgeCaption").textContent = ev.caption;
  }
  if (ev.stage === "guardrail") {
    setStage("guardrail", b => {
      if (d.blocked) {
        b.appendChild(chip("ESCALATED", "amber"));
        b.appendChild(el("p", "Blocked before any model ran: " + d.reason + ". A human gets the approval request — see the Result card."));
      } else {
        b.appendChild(chip("ALLOWED", "green"));
        b.appendChild(el("p", "No destructive pattern matched. The issue proceeds to the agents."));
      }
    });
  } else if (ev.stage === "triage") {
    setStage("triage", b => {
      b.appendChild(chip(d.kind || "issue", "blue"));
      b.appendChild(el("p", d.summary || ""));
      if (d.acceptance && d.acceptance.length) {
        const ul = el("ul", null, "steps");
        d.acceptance.forEach(a => ul.appendChild(el("li", a)));
        b.appendChild(ul);
      }
    });
  } else if (ev.stage === "plan") {
    setStage("plan", b => {
      const ul = el("ul", null, "steps");
      (d.steps || []).forEach(s => ul.appendChild(el("li", s)));
      b.appendChild(ul);
      if (d.expected_files) b.appendChild(el("p", "Expected files: " + d.expected_files.join(", ")));
    });
  } else if (ev.stage === "code") {
    setStage("code", b => {
      b.appendChild(el("p", "Files changed: " + (d.changed || []).join(", ")));
      if (d.diff) b.appendChild(el("pre", d.diff));
    });
  } else if (ev.stage === "tests") {
    setStage("tests", b => {
      b.appendChild(chip(d.tests_ok ? "PASSING" : "FAILING", d.tests_ok ? "green" : "red"));
      b.appendChild(el("p", "Discovered tests: " + d.tests_before + " → " + d.tests_after));
      if (d.test_log_tail) b.appendChild(el("pre", d.test_log_tail));
    });
  } else if (ev.stage === "review") {
    setStage("review", b => {
      const ok = d.verdict === "approve";
      b.appendChild(chip((d.verdict || "").toUpperCase(), ok ? "green" : "red"));
      b.appendChild(el("p", d.notes || ""));
    });
  } else if (ev.stage === "done") {
    setStage("done", b => {
      const r = d.result || {};
      b.appendChild(el("div", r.passed ? "✔ Passed — PR-ready" : "✘ Not PR-ready", "banner " + (r.passed ? "pass" : "fail")));
      if (d.pr_body) b.appendChild(el("pre", d.pr_body));
    });
  }
}

function renderResultsCard(card) {
  if (!card) return;
  $("judgeResultsPanel").style.display = "block";
  const box = $("judgeResults"); box.textContent = "";
  box.appendChild(el("div", card.overall === "pass" ? "✔ Overall: PASS" : card.overall === "escalated" ? "⛔ Overall: ESCALATED" : "Overall: " + card.overall.toUpperCase(), "banner " + (card.overall === "pass" ? "pass" : card.overall === "escalated" ? "esc" : "fail")));
  const ul = el("ul", null, "steps");
  card.stages.forEach(s => {
    const ms = s.elapsed_ms === null || s.elapsed_ms === undefined ? "" : " · " + s.elapsed_ms + " ms";
    ul.appendChild(el("li", s.stage + ": " + s.status.toUpperCase() + (s.detail ? " — " + s.detail : "") + ms));
  });
  box.appendChild(ul);
  if (card.tests_delta !== null && card.tests_delta !== undefined)
    box.appendChild(el("p", "Tests: " + card.tests_before + " → " + card.tests_after + " (" + (card.tests_delta >= 0 ? "+" : "") + card.tests_delta + ")"));
  if (card.cost) {
    const c = card.cost;
    const label = c.method === "mock_no_api_call" ? "API cost: $0.00 (mock run — no API call made)"
      : c.method === "no_model_calls" ? "API cost: $0.00 (no model calls — guardrail)"
      : "Est. API cost: $" + c.total_usd_est.toFixed(4) + " (char-count estimate — the API does not expose usage on this path; per-role below)";
    box.appendChild(el("p", label));
    const roles = Object.keys(c.per_role || {});
    if (roles.length) box.appendChild(el("p", roles.map(r => r + " $" + c.per_role[r].cost_usd_est.toFixed(4)).join(" · "), "hint"));
  }
  if (card.links) {
    const p = el("p");
    const mk = (href, label) => { const a = el("a", label); a.href = href; a.target = "_blank"; p.appendChild(a); p.appendChild(document.createTextNode(" · ")); };
    if (card.links.pr_url) mk(card.links.pr_url, "This run's PR");
    (card.links.live_prs || []).forEach((u, i) => mk(u, "Live PR #" + [16,17,18][i]));
    mk(card.links.eval_scorecard, "Eval scorecard");
    mk(card.links.generalization, "Generalization run");
    box.appendChild(p);
  }
}

async function poll() {
  const snap = await (await fetch("/api/run/" + currentRun)).json();
  while (rendered < snap.events.length) { renderEvent(snap.events[rendered]); rendered++; }
  if (snap.status === "running") return;
  clearInterval(poller);
  if (snap.judge_mode) renderResultsCard(snap.results_card);
  $("runBtn").disabled = false;
  const jb = $("judgeBtn"); if (jb) { jb.disabled = false; if (snap.judge_mode) $("judgeStatus").textContent = "Judge Mode complete — see the results card."; }
  if (snap.status === "escalated") {
    $("runStatus").textContent = "Escalated by the guardrail — no agent ran, nothing was changed.";
    setStage("done", b => {
      const esc = snap.events.find(e => e.stage === "guardrail" && e.data.blocked);
      b.appendChild(el("div", "⛔ Escalated to a human — no PR opened", "banner esc"));
      if (esc) {
        b.appendChild(el("p", "Reason: " + esc.data.reason));
        b.appendChild(el("pre", JSON.stringify(esc.data.request, null, 2)));
      }
    });
  } else if (snap.status === "error") {
    $("runStatus").textContent = "Run error: " + snap.error;
  } else {
    const r = snap.result || {};
    $("runStatus").textContent = r.passed ? "Run complete — passed." : "Run complete — not PR-ready.";
    if (r.pr_url) {
      setStage("done", b => {
        b.appendChild(el("div", "✔ Pull request opened", "banner pass"));
        const a = el("a", r.pr_url); a.href = r.pr_url; a.target = "_blank";
        b.appendChild(a);
        if (r.pr_body) b.appendChild(el("pre", r.pr_body));
      });
    } else if (r.pr_body && rendered === snap.events.length) {
      // done event already rendered the PR body; nothing more to add
    }
  }
}

$("judgeBtn").onclick = async () => {
  resetTimeline();
  $("judgeResultsPanel").style.display = "none";
  $("judgeBtn").disabled = true; $("runBtn").disabled = true;
  $("judgeStatus").textContent = "Judge Mode running — narration appears as stages fire…";
  const resp = await fetch("/api/judge/run", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({issue_id: "tier1", mode: "mock"})});
  const data = await resp.json();
  if (!data.run_id) { $("judgeStatus").textContent = "Error: " + (data.error || "unknown"); $("judgeBtn").disabled = false; $("runBtn").disabled = false; return; }
  currentRun = data.run_id;
  poller = setInterval(poll, 500);
  poll();
};

$("runBtn").onclick = async () => {
  if (!selectedIssue) return;
  resetTimeline();
  $("runBtn").disabled = true;
  $("runStatus").textContent = "Starting…";
  const resp = await fetch("/api/run", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({issue_id: selectedIssue, mode: mode, open_pr: $("openPr").checked})});
  const data = await resp.json();
  if (!data.run_id) { $("runStatus").textContent = "Error: " + (data.error || "unknown"); $("runBtn").disabled = false; return; }
  currentRun = data.run_id;
  $("runStatus").textContent = "Running (" + mode + ")…";
  poller = setInterval(poll, 500);
  poll();
};

$("breakBtn").onclick = async () => {
  const resp = await fetch("/api/guardrail", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({title: $("breakTitle").value, body: $("breakBody").value})});
  const data = await resp.json();
  const box = $("breakResult"); box.textContent = "";
  if (!data.blocked) {
    box.appendChild(chip("ALLOWED", "green"));
    box.appendChild(el("p", "No destructive pattern matched — this would proceed to the agents."));
    return;
  }
  box.appendChild(chip("ESCALATED", "amber"));
  box.appendChild(el("p", "Reason: " + data.reason + ". No model ran; no files changed; no PR opened. The human reviewer gets this handoff:"));
  const ul = el("ul", null, "steps");
  data.handoff.human_options.forEach(o => ul.appendChild(el("li", o.label + " — " + o.effect)));
  box.appendChild(ul);
  box.appendChild(el("pre", data.handoff_markdown));
  // Approve-and-resume: record a human decision on this handoff.
  const dec = el("div");
  const note = el("p", "Record a decision: reject / handle manually close this with no agent run; re-scope attaches the Tier 1 issue as the narrower replacement and marks it resumable via pipeline.resume.", "hint");
  dec.appendChild(note);
  ["reject","handle_manually","rescope"].forEach(d => {
    const b = el("button", d);
    b.style.marginRight = "8px";
    b.onclick = async () => {
      const payload = {request: data.handoff, decision: d, decided_by: "Demo operator", decided_at: new Date().toISOString(),
        rescoped_issue: d === "rescope" ? {title: "Fix off-by-one in pagination helper", body: "paginate() returns one item short on full pages."} : null};
      const r = await (await fetch("/api/approval/decide", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(payload)})).json();
      const out = el("pre", r.error ? ("Error: " + r.error) : JSON.stringify(r.request.decision_record, null, 2) + "\nwill_resume: " + r.will_resume);
      dec.appendChild(out);
    };
    dec.appendChild(b);
  });
  box.appendChild(dec);
};

loadIssues();
</script>
</body>
</html>
"""


PAGE_V3 = r"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DevOps as a Service — demo console v3</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<script>
  // Apply the persisted theme before first paint (default: light).
  try { document.documentElement.dataset.theme =
    localStorage.getItem("daas-v3-theme") || "light"; } catch (e) {}
</script>
<style>
  :root{
    --page:#ECECE9;
    --app:#F7F7F4;
    --card:#FFFFFF;
    --line:#E5E5E0;
    --line-soft:#E1E1D9;
    --line-info:#C8C8BF;
    --ink:#151B28;
    --body:#3A4356;
    --mut:#49536A;
    --faint:#6E7690;
    --label:#55607A;
    --acc:#4350C8;
    --acc-deep:#35409F;
    --acc-tint:#EEF0FB;
    --navy:#1D2A47;
    --grn:#1F7A3D;
    --grn-tint:#EAF5EE;
    --amb:#8A5D05;
    --amb-tint:#FAF2DE;
    --red:#A52A2A;
    --red-tint:#FBF0F0;
    --mono:"IBM Plex Mono",ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
    --sans:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans",Helvetica,Arial,sans-serif;
    --shadow:0 1px 2px rgba(23,26,33,.04),0 10px 30px rgba(23,26,33,.05);
  }
  /* ---------- dark theme (approved v3 dark mockup tokens) ---------- */
  html[data-theme="dark"]{
    --page:#07080A;
    --app:#0E1116;
    --card:#151922;
    --line:#232A37;
    --line-soft:#1D232E;
    --line-info:#343D52;
    --ink:#EDF0F7;
    --body:#C3C9D8;
    --mut:#9AA3B8;
    --faint:#79839A;
    --label:#8B94AC;
    --acc:#8B94F0;
    --acc-deep:#A5ADF2;
    --acc-tint:#1D2340;
    --navy:#8B94F0;
    --grn:#4CC38A;
    --grn-tint:#122A1D;
    --amb:#E8AE45;
    --amb-tint:#29200E;
    --red:#F0938A;
    --red-tint:#2B181A;
    --shadow:0 1px 2px rgba(0,0,0,.40),0 10px 30px rgba(0,0,0,.35);
  }
  html[data-theme="dark"] .frame{border-color:#232A37;box-shadow:0 24px 60px rgba(0,0,0,.55)}
  html[data-theme="dark"] .logo{color:#C9D2E8;box-shadow:0 1px 2px rgba(0,0,0,.4)}
  html[data-theme="dark"] .theme{background:#171C26}
  html[data-theme="dark"] .theme button.on{background:#262E3D;box-shadow:none}
  html[data-theme="dark"] .btn-navy{background:#8B94F0;color:#0D1017}
  html[data-theme="dark"] .btn-navy:hover{background:#9BA3F3}
  html[data-theme="dark"] .issue.sel{border-color:#3D4470}
  html[data-theme="dark"] .issue.sel .tic{background:#252C4D;border-color:#3D4470}
  html[data-theme="dark"] .seg{background:#171C26}
  html[data-theme="dark"] .seg button.on{background:#262E3D;box-shadow:none}
  html[data-theme="dark"] .step.done .ring{border-color:#2F7D4E}
  html[data-theme="dark"] .conn.done{background:#2F7D4E}
  html[data-theme="dark"] .conn.done:after{background-image:linear-gradient(90deg,transparent,rgba(255,255,255,.45),transparent)}
  html[data-theme="dark"] .conn:after{background-image:linear-gradient(90deg,transparent,rgba(139,148,240,.38),transparent)}
  html[data-theme="dark"] .stage:before{border-color:#4A5266}
  html[data-theme="dark"] .stage.idle:before{border-color:#414A5E}
  html[data-theme="dark"] .stage.run{border-color:#3D4470}
  html[data-theme="dark"] .stage.run:hover{border-color:#3D4470}
  html[data-theme="dark"] .stage.run:after{background:linear-gradient(90deg,transparent,rgba(139,148,240,.55),transparent);
    background-size:200% 100%}
  html[data-theme="dark"] .stage.run h3 .sic{border-color:#3D4470}
  html[data-theme="dark"] .kindtag.code{background:#1E242F}
  html[data-theme="dark"] pre{background:#0C0F15;color:#D6DBE8}
  html[data-theme="dark"] .diff-add{color:#4CC38A;background:#12271C}
  html[data-theme="dark"] .diff-del{color:#F0938A;background:#2B181A}
  html[data-theme="dark"] .prog{background:#232A37}
  html[data-theme="dark"] input[type=text],html[data-theme="dark"] textarea{background:#0C0F15}
  html[data-theme="dark"] input[type=text]:focus,html[data-theme="dark"] textarea:focus{box-shadow:0 0 0 3px rgba(139,148,240,.28)}
  html[data-theme="dark"] .issue:hover{background:#1A2029}
  html[data-theme="dark"] .kpi:hover{border-color:#2E3646}
  html[data-theme="dark"] .stage:hover{border-color:#2E3646}
  html[data-theme="dark"] .btn-line:hover{border-color:#39445C}
  html[data-theme="dark"] .step.run .ring{animation-name:ringpulse-d}
  html[data-theme="dark"] .statuschip .dot{animation-name:breathe-d}
  html[data-theme="dark"] .kpi:after{background:linear-gradient(105deg,transparent 42%,rgba(139,148,240,.10) 50%,transparent 58%)}
  html[data-theme="dark"] .now:after{background:linear-gradient(100deg,transparent 35%,rgba(139,148,240,.07) 50%,transparent 65%);
    background-size:260% 100%}

  *{box-sizing:border-box}
  body{margin:0;background:var(--page);color:var(--ink);font-family:var(--sans);
    -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
  .frame{max-width:1456px;margin:26px auto;background:var(--app);
    border:1px solid #DFDFD9;border-radius:22px;box-shadow:0 24px 60px rgba(23,26,33,.10);
    padding:0 44px 40px;overflow:hidden}
  .ic{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.5;
    stroke-linecap:round;stroke-linejoin:round;flex:none}
  .ic.sm{width:14px;height:14px}
  .ic.lg{width:20px;height:20px}
  .lab{font-size:10.5px;font-weight:600;letter-spacing:.16em;text-transform:uppercase;color:var(--label)}
  .num{font-variant-numeric:tabular-nums}

  /* ---------- top bar ---------- */
  .topbar{display:flex;align-items:center;gap:14px;padding:20px 0 18px;
    border-bottom:1px solid var(--line-info)}
  .logo{width:38px;height:38px;border-radius:10px;background:var(--card);
    border:1px solid var(--line);display:flex;align-items:center;justify-content:center;
    color:var(--navy);box-shadow:0 1px 2px rgba(23,26,33,.05)}
  .brand .name{font-size:15px;font-weight:600;letter-spacing:-.01em;line-height:1.15}
  .brand .sub{font-size:12px;color:var(--mut);line-height:1.2}
  .topbar .sp{flex:1}
  .statuschip{display:flex;align-items:center;gap:8px;font-size:12.5px;font-weight:500;
    color:var(--body);background:var(--card);border:1px solid var(--line);
    border-radius:999px;padding:7px 13px}
  .dot{width:7px;height:7px;border-radius:50%;background:var(--grn);flex:none}
  .dot.pulse{animation:dotpulse 2.2s ease-in-out infinite}
  .theme{display:flex;background:#EBEBE6;border:1px solid var(--line);border-radius:999px;padding:3px}
  .theme button{display:flex;align-items:center;gap:6px;border:0;cursor:pointer;background:transparent;
    color:var(--mut);font-family:inherit;font-size:12.5px;font-weight:500;
    padding:5px 12px;border-radius:999px}
  .theme button.on{background:var(--card);color:var(--ink);box-shadow:0 1px 3px rgba(23,26,33,.12)}

  /* ---------- hero ---------- */
  .hero{padding:30px 0 4px}
  .eyebrow{display:flex;align-items:center;gap:8px;font-size:11px;font-weight:600;
    letter-spacing:.18em;text-transform:uppercase;color:var(--acc)}
  .eyebrow:before{content:"";width:22px;height:1px;background:var(--acc);opacity:.55}
  h1{margin:12px 0 8px;font-size:31px;font-weight:600;letter-spacing:-.022em;line-height:1.15}
  .lede{margin:0;max-width:780px;font-size:15px;line-height:1.6;color:var(--body)}
  .lede b{color:var(--ink);font-weight:600}

  /* KPI strip */
  .kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:24px 0 2px}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;
    padding:15px 17px 14px;box-shadow:var(--shadow)}
  .kpi .top{display:flex;align-items:flex-start;justify-content:space-between}
  .kpi .num{font-size:27px;font-weight:600;letter-spacing:-.02em;line-height:1.1}
  .kpi .num .unit{font-size:14px;color:var(--mut);font-weight:500}
  .kpi .ic{color:var(--faint)}
  .kpi .lab{margin-top:4px}

  /* ---------- layout ---------- */
  main{display:grid;grid-template-columns:348px 1fr;gap:20px;margin-top:22px;align-items:start}
  .card{background:var(--card);border:1px solid var(--line);border-radius:16px;
    padding:19px 20px;margin-bottom:18px;box-shadow:var(--shadow)}
  .card h2{display:flex;align-items:center;gap:8px;margin:0 0 8px;
    font-size:10.5px;font-weight:600;letter-spacing:.16em;text-transform:uppercase;color:var(--label)}
  .card h2 .ic{width:14px;height:14px;color:var(--label)}
  .hint{font-size:13px;color:var(--mut);line-height:1.55;margin:0 0 13px}

  /* judge mode */
  .btn-navy{width:100%;display:flex;align-items:center;justify-content:center;gap:9px;
    padding:12px;font-family:inherit;font-size:14.5px;font-weight:600;border:0;border-radius:11px;
    background:var(--navy);color:#fff;cursor:pointer}
  .btn-navy .ic{width:15px;height:15px}
  .btn-navy:disabled{opacity:.5;cursor:default}
  .okline{display:flex;align-items:center;gap:7px;margin-top:11px;font-size:12.5px;color:var(--grn);min-height:17px}
  .okline .ic{width:14px;height:14px}

  /* issue list */
  .issue{display:flex;gap:11px;padding:11px 12px;margin:0 -6px;border-radius:11px;cursor:pointer;
    border:1px solid transparent}
  .issue + .issue{border-top:1px solid var(--line-soft)}
  .issue .tic{width:30px;height:30px;border-radius:8px;background:var(--app);
    border:1px solid var(--line-soft);display:flex;align-items:center;justify-content:center;color:var(--mut);flex:none}
  .issue .tic .ic{width:15px;height:15px}
  .issue.sel{background:var(--acc-tint);border-color:#B4BAE6}
  .issue.sel .tic{background:#fff;border-color:#B4BAE6;color:var(--acc)}
  html[data-theme="dark"] .issue.sel .tic{background:#252C4D}
  .issue .label{font-size:12px;font-weight:600;color:var(--ink);display:flex;align-items:center;gap:8px}
  .issue .title{font-size:13.5px;font-weight:500;margin-top:1px}
  .issue .blurb{font-size:12.5px;color:var(--mut);margin-top:1px;line-height:1.45}
  .tag{font-size:9px;font-weight:700;letter-spacing:.11em;padding:2px 6px;border-radius:5px;
    color:var(--amb);background:var(--amb-tint);text-transform:uppercase}

  /* mode toggle */
  .seg{display:flex;background:#EBEBE6;border:1px solid var(--line);border-radius:11px;padding:3px;margin-bottom:12px}
  .seg button{flex:1;display:flex;align-items:center;justify-content:center;gap:7px;
    padding:8px;background:transparent;color:var(--mut);border:0;border-radius:8px;cursor:pointer;
    font-family:inherit;font-size:13px;font-weight:500}
  .seg button.on{background:var(--card);color:var(--ink);box-shadow:0 1px 3px rgba(23,26,33,.12)}
  .seg .dot{width:6px;height:6px}
  .btn-line{width:100%;display:flex;align-items:center;justify-content:center;gap:8px;
    padding:11px;font-family:inherit;font-size:14px;font-weight:600;border:1px solid var(--line);
    border-radius:11px;background:var(--card);color:var(--ink);cursor:pointer}
  .btn-line:disabled{opacity:.5;cursor:default}
  .btn-line.sm{width:auto;padding:8px 14px;font-size:13px}
  .runline{display:flex;align-items:center;gap:7px;margin-top:11px;font-size:12.5px;color:var(--body);min-height:17px}
  label.check{display:flex;gap:8px;align-items:center;font-size:13.5px;color:var(--body);margin:2px 0 12px}
  label.check.disabled{color:var(--mut)}
  label.check input{accent-color:var(--acc)}

  /* ---------- stepper ---------- */
  .stepper{display:flex;align-items:flex-start;background:var(--card);border:1px solid var(--line);
    border-radius:16px;padding:20px 24px 16px;margin-bottom:18px;box-shadow:var(--shadow);overflow-x:auto}
  .step{flex:0 0 auto;text-align:center;width:84px}
  .step .ring{width:34px;height:34px;margin:0 auto;border-radius:50%;display:flex;align-items:center;
    justify-content:center;border:1.5px solid var(--line);background:var(--card);color:var(--faint)}
  .step .ring .ic{width:15px;height:15px}
  .step.done .ring{border-color:#93CCA9;background:var(--grn-tint);color:var(--grn)}
  .step.run .ring{border-color:var(--acc);color:var(--acc);background:var(--acc-tint);
    animation:ringpulse 2.2s ease-out infinite}
  .step .name{margin-top:8px;font-size:11px;font-weight:600;letter-spacing:.07em;
    text-transform:uppercase;color:var(--mut)}
  .step.done .name{color:var(--ink)}
  .step.run .name{color:var(--acc-deep)}
  .step .kind{font-size:9px;font-weight:600;letter-spacing:.15em;color:var(--label);margin-top:1px}
  .conn{flex:1;min-width:14px;height:1.5px;background:var(--line-info);margin-top:17px;border-radius:2px;position:relative;overflow:hidden}
  .conn.done{background:#93CCA9}
  .conn.part{background:var(--line)}
  .conn.part i{position:absolute;inset:0;width:48%;background:var(--acc);border-radius:2px;display:block}
  .conn.part i:after{content:"";position:absolute;inset:0;
    background:linear-gradient(90deg,transparent,rgba(255,255,255,.75),transparent);
    animation:sweep 2.6s ease-in-out infinite}

  /* ---------- narration ---------- */
  .now{display:flex;gap:13px;align-items:flex-start;background:var(--card);
    border:1px solid var(--line);border-radius:16px;padding:16px 19px;margin-bottom:18px;box-shadow:var(--shadow)}
  .now .pill{display:flex;align-items:center;gap:7px;flex:0 0 auto;font-size:10px;font-weight:700;
    letter-spacing:.16em;color:var(--acc-deep);background:var(--acc-tint);
    padding:5px 10px;border-radius:999px;margin-top:2px}
  .now .pill .dot{background:var(--acc)}
  .now p{margin:0;font-size:15px;line-height:1.55;color:var(--body);animation:fadeUp .9s ease both}
  .now p .who{color:var(--ink);font-weight:600}
  .now .t{margin-left:auto;flex:0 0 auto;font-family:var(--mono);font-size:11.5px;color:var(--mut);padding-top:4px}

  /* ---------- stage timeline ---------- */
  .timeline{position:relative;margin:2px 0 4px 15px;padding-left:32px}
  .timeline:before{content:"";position:absolute;left:0;top:14px;bottom:14px;width:1px;background:var(--line-info)}
  .stage{position:relative;background:var(--card);border:1px solid var(--line);border-radius:16px;
    padding:16px 19px;margin-bottom:13px;box-shadow:var(--shadow)}
  .stage:before{content:"";position:absolute;left:-37.5px;top:23px;width:9px;height:9px;border-radius:50%;
    background:var(--app);border:2px solid #A9A99D}
  .stage.done:before{border-color:var(--grn);background:var(--grn-tint)}
  .stage.run{border-color:#A9AFDE}
  .stage.run:before{border-color:var(--acc);background:var(--acc);animation:dotpulse 2.2s ease-in-out infinite}
  .stage.run:after{content:"";position:absolute;top:-1px;left:12%;right:12%;height:2px;border-radius:2px;
    background:linear-gradient(90deg,transparent,rgba(67,80,200,.60),transparent);
    background-size:200% 100%;animation:edge 3.4s linear infinite}
  .stage.idle h3 .elapsed{color:var(--label)}
  .stage.idle:before{border-color:#B9B9AE}
  .stage h3{margin:0;font-size:15.5px;font-weight:600;display:flex;align-items:center;gap:9px;letter-spacing:-.01em}
  .stage h3 .sic{width:28px;height:28px;border-radius:8px;background:var(--app);border:1px solid var(--line-soft);
    display:flex;align-items:center;justify-content:center;color:var(--mut)}
  .stage h3 .sic .ic{width:14.5px;height:14.5px}
  .stage.run h3 .sic{background:var(--acc-tint);border-color:#B4BAE6;color:var(--acc)}
  html[data-theme="dark"] .stage.run h3 .sic{background:var(--acc-tint)}
  .stage h3 .elapsed{margin-left:auto;font-family:var(--mono);font-size:11.5px;color:var(--mut);font-weight:400;
    display:flex;align-items:center;gap:7px}
  .kindtag{font-size:9px;font-weight:700;letter-spacing:.12em;padding:2.5px 7px;border-radius:5px;text-transform:uppercase}
  .kindtag.code{color:var(--body);background:#F0F0EB}
  .kindtag.agent{color:var(--acc-deep);background:var(--acc-tint)}
  .stage .body{margin-top:9px;font-size:13.5px;line-height:1.6;color:var(--body)}
  .stage .body p{margin:5px 0}
  .stage .body .empty{color:var(--mut);font-size:13px}
  ul.steps{margin:5px 0;padding-left:18px}
  ul.steps li{margin:2px 0}
  ul.steps li::marker{color:var(--mut)}
  .chip{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:600;
    padding:3px 9px;border-radius:999px}
  .chip .dot{width:6px;height:6px}
  .chip.pass{color:var(--grn);background:var(--grn-tint)}
  .chip.fail{color:var(--red);background:var(--red-tint)}
  .chip.amb{color:var(--amb);background:var(--amb-tint)}
  .chip.pend{color:var(--body);background:var(--line)}
  pre{background:#FAFAF7;border:1px solid var(--line-soft);border-radius:10px;padding:11px 13px;
    overflow:auto;font-family:var(--mono);font-size:12px;line-height:1.55;margin:9px 0 2px;
    white-space:pre-wrap;word-break:break-word;color:#2E3442}
  .diff-add{color:#1B6B3A;background:#EDF7EF;display:block;margin:0 -13px;padding:0 13px}
  .diff-del{color:#A52A2A;background:#FBF1F1;display:block;margin:0 -13px;padding:0 13px}
  .prog{height:3px;background:#E3E3DB;border-radius:3px;margin-top:12px;overflow:hidden;position:relative}
  .prog i{display:block;height:100%;width:40%;background:var(--acc);border-radius:3px;position:relative;overflow:hidden;
    animation:ind 1.7s ease-in-out infinite alternate}
  .prog i:after{content:"";position:absolute;inset:0;
    background:linear-gradient(90deg,transparent,rgba(255,255,255,.65),transparent);
    animation:sweep 2.6s ease-in-out infinite}
  @keyframes ind{from{transform:translateX(-30%)}to{transform:translateX(190%)}}
  .vbanner{font-weight:600;font-size:13.5px;padding:11px 13px;border-radius:10px;margin-bottom:8px}
  .vbanner.pass{color:var(--grn);background:var(--grn-tint)}
  .vbanner.fail{color:var(--red);background:var(--red-tint)}
  .vbanner.esc{color:var(--amb);background:var(--amb-tint)}

  /* ---------- results card ---------- */
  .results .rhead{display:flex;align-items:center;gap:10px;margin-bottom:4px}
  .results .rhead .ttl{font-size:16px;font-weight:600;letter-spacing:-.01em}
  .pill-pass{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;
    letter-spacing:.08em;color:var(--grn);background:var(--grn-tint);padding:4px 10px;border-radius:999px;text-transform:uppercase}
  .pill-fail{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;
    letter-spacing:.08em;color:var(--red);background:var(--red-tint);padding:4px 10px;border-radius:999px;text-transform:uppercase}
  .pill-esc{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;
    letter-spacing:.08em;color:var(--amb);background:var(--amb-tint);padding:4px 10px;border-radius:999px;text-transform:uppercase}
  .pill-line{font-size:10.5px;font-weight:600;letter-spacing:.1em;color:var(--body);
    border:1px solid var(--line);padding:4px 9px;border-radius:999px;text-transform:uppercase}
  .rsub{font-size:12.5px;color:var(--mut);margin:0 0 6px}
  table.score{width:100%;border-collapse:collapse;margin-top:8px;font-size:13.5px}
  table.score th{font-size:10px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--label);
    text-align:left;padding:7px 10px;border-bottom:1px solid var(--line-info)}
  table.score td{padding:9px 10px;border-bottom:1px solid var(--line-soft);vertical-align:middle;color:var(--body)}
  table.score tr:last-child td{border-bottom:0}
  table.score .stg{font-weight:600;color:var(--ink)}
  table.score .ms{font-family:var(--mono);font-size:11.5px;color:var(--mut);text-align:right}
  table.score th.ms{text-align:right}
  .stats{display:flex;gap:30px;flex-wrap:wrap;margin-top:14px;padding-top:14px;border-top:1px solid var(--line-info)}
  .stats .v{font-size:16px;font-weight:600;letter-spacing:-.01em}
  .stats .k{font-size:10px;font-weight:600;letter-spacing:.13em;text-transform:uppercase;color:var(--label);margin-top:1px}
  .rolesline{font-size:12px;color:var(--mut);margin-top:10px}
  .links{display:flex;gap:18px;flex-wrap:wrap;margin-top:14px;font-size:13px}
  .links a{display:inline-flex;align-items:center;gap:5px;color:var(--acc-deep);text-decoration:none;font-weight:500}
  .links a .ic{width:13px;height:13px}

  /* ---------- break it ---------- */
  .cols{display:grid;grid-template-columns:1fr 1fr;gap:20px}
  input[type=text],textarea{width:100%;background:#FBFBF9;color:var(--ink);
    border:1px solid var(--line);border-radius:10px;padding:10px 12px;font-size:13.5px;
    font-family:inherit;margin-bottom:9px}
  textarea{min-height:68px;resize:vertical;line-height:1.5}
  input[type=text]:focus,textarea:focus{outline:none;border-color:var(--acc);box-shadow:0 0 0 3px var(--acc-tint)}
  .esc{display:flex;gap:12px;align-items:flex-start}
  .esc .eic{width:34px;height:34px;border-radius:9px;background:var(--amb-tint);color:var(--amb);
    display:flex;align-items:center;justify-content:center;flex:none}
  .esc .eic.ok{background:var(--grn-tint);color:var(--grn)}
  .esc .et{font-size:15.5px;font-weight:600;letter-spacing:-.01em}
  .verdict{font-size:13.5px;line-height:1.6;color:var(--body);margin:10px 0 0}
  .decrow{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}

  .foot{margin-top:22px;font-size:12px;color:var(--mut);text-align:center}

  /* ---------- micro-animations ---------- */
  @keyframes dotpulse{0%,100%{opacity:1}50%{opacity:.4}}
  @keyframes ringpulse{0%{box-shadow:0 0 0 0 rgba(67,80,200,.30)}70%{box-shadow:0 0 0 8px rgba(67,80,200,0)}100%{box-shadow:0 0 0 0 rgba(67,80,200,0)}}
  @keyframes ringpulse-d{0%{box-shadow:0 0 0 0 rgba(139,148,240,.32)}70%{box-shadow:0 0 0 8px rgba(139,148,240,0)}100%{box-shadow:0 0 0 0 rgba(139,148,240,0)}}
  @keyframes sweep{0%{transform:translateX(-110%)}60%,100%{transform:translateX(240%)}}
  @keyframes fadeUp{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
  @keyframes edge{0%{background-position:120% 0}100%{background-position:-120% 0}}

  /* ---------- ambient layer (alive at rest, always slow & quiet) ---------- */
  .statuschip .dot,.breathe{animation:breathe 4.6s ease-in-out infinite}
  @keyframes breathe{0%,100%{transform:scale(1);opacity:.8;box-shadow:0 0 0 0 rgba(31,122,61,.18)}
    50%{transform:scale(1.18);opacity:1;box-shadow:0 0 0 5px rgba(31,122,61,0)}}
  @keyframes breathe-d{0%,100%{transform:scale(1);opacity:.8;box-shadow:0 0 0 0 rgba(76,195,138,.22)}
    50%{transform:scale(1.18);opacity:1;box-shadow:0 0 0 5px rgba(76,195,138,0)}}
  .conn:after{content:"";position:absolute;inset:0;background-repeat:no-repeat;
    background-size:34px 100%;background-position:-40px 0;
    background-image:linear-gradient(90deg,transparent,rgba(67,80,200,.35),transparent);
    animation:connflow 6.5s linear infinite}
  .conn.done:after{background-image:linear-gradient(90deg,transparent,rgba(255,255,255,.85),transparent)}
  .conn.part:after{display:none}
  @keyframes connflow{to{background-position:calc(100% + 40px) 0}}
  .kpi{position:relative;overflow:hidden}
  .kpi .num{animation:fadeUp .8s cubic-bezier(.22,.61,.36,1) both}
  .kpi:nth-child(2) .num{animation-delay:.07s}
  .kpi:nth-child(3) .num{animation-delay:.14s}
  .kpi:nth-child(4) .num{animation-delay:.21s}
  .kpi:nth-child(5) .num{animation-delay:.28s}
  .kpi:after{content:"";position:absolute;inset:0;pointer-events:none;
    background:linear-gradient(105deg,transparent 42%,rgba(67,80,200,.08) 50%,transparent 58%);
    transform:translateX(-130%);animation:kpisheen 2.4s ease .35s both}
  @keyframes kpisheen{to{transform:translateX(130%)}}
  .now{position:relative;overflow:hidden}
  .now>*{position:relative;z-index:1}
  .now:after{content:"";position:absolute;inset:0;pointer-events:none;
    background:linear-gradient(100deg,transparent 35%,rgba(67,80,200,.06) 50%,transparent 65%);
    background-size:260% 100%;background-position:130% 0;animation:nowscan 7.5s ease-in-out infinite}
  @keyframes nowscan{0%{background-position:130% 0}55%,100%{background-position:-130% 0}}
  .card,.kpi,.stage,.issue,.step .ring,.btn-navy,.btn-line,.seg button,.theme button,.statuschip,.conn{
    transition:border-color .3s ease,box-shadow .3s ease,background-color .3s ease,color .3s ease}
  .issue:hover{background:#FCFCF9}
  html[data-theme="dark"] .issue:hover{background:#1A2029}
  .kpi:hover{border-color:#DAD9CF}
  .stage:hover{border-color:#DBDBD2}
  .stage.run:hover{border-color:#A9AFDE}
  .btn-navy:hover{background:#16223C}
  .btn-line:hover{border-color:#CFCFC4}
  .links a{transition:color .25s ease}
  .links a:hover{color:var(--acc)}

  @media (max-width: 1000px){
    main{grid-template-columns:1fr}
    .cols{grid-template-columns:1fr}
    .kpis{grid-template-columns:repeat(2,1fr)}
    .frame{padding:0 18px 28px}
  }
</style>
</head>
<body>
<div class="frame">

  <!-- ======================= top bar ======================= -->
  <div class="topbar">
    <div class="logo">
      <svg class="ic lg" viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
    </div>
    <div class="brand">
      <div class="name">DevOps as a Service</div>
      <div class="sub">Demo console</div>
    </div>
    <div class="sp"></div>
    <div class="statuschip"><span class="dot"></span><span id="metaChipText">Bench verified · loading…</span></div>
    <div class="theme">
      <button id="themeLight"><svg class="ic sm" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>Light</button>
      <button id="themeDark"><svg class="ic sm" viewBox="0 0 24 24"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>Dark</button>
    </div>
  </div>

  <!-- ======================= hero ======================= -->
  <div class="hero">
    <div class="eyebrow">Meta Global AI Developer Hackathon · Indie Track</div>
    <h1>File an issue. The agents open the pull request.</h1>
    <p class="lede">Four agents — <b>triage, planner, coder, reviewer</b> — do the work.
      A <b>deterministic guardrail</b> runs before any model, and anything destructive
      escalates to a human instead.</p>
    <div class="kpis">
      <div class="kpi">
        <div class="top"><div class="num"><span id="kpiScenarios">–</span></div>
          <svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/></svg></div>
        <div class="lab">DevOps scenarios passed live</div>
      </div>
      <div class="kpi">
        <div class="top"><div class="num" id="kpiTests">–</div>
          <svg class="ic" viewBox="0 0 24 24"><path d="M10 2v6L4.5 18a2 2 0 0 0 1.8 3h11.4a2 2 0 0 0 1.8-3L14 8V2"/><path d="M8.5 2h7"/><path d="M7 16h10"/></svg></div>
        <div class="lab">Net new tests across the bench</div>
      </div>
      <div class="kpi">
        <div class="top"><div class="num" id="kpiCost">–</div>
          <svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 6v2m0 8v2"/></svg></div>
        <div class="lab">Est. API cost per fixed issue</div>
      </div>
      <div class="kpi">
        <div class="top"><div class="num" id="kpiPrs">–</div>
          <svg class="ic" viewBox="0 0 24 24"><path d="M6 3v12"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg></div>
        <div class="lab">Live PRs opened by the pipeline</div>
      </div>
      <div class="kpi">
        <div class="top"><div class="num" id="kpiScore">–</div>
          <svg class="ic" viewBox="0 0 24 24"><path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/></svg></div>
        <div class="lab">Weighted internal scorecard</div>
      </div>
    </div>
  </div>

  <main>
    <!-- ======================= left rail ======================= -->
    <div>
      <div class="card">
        <h2><svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>Judge Mode — self-guided</h2>
        <p class="hint">One click, no operator needed: runs the Tier 1 issue end to end with
          narration as each stage fires, and closes on a graded results card.</p>
        <button class="btn-navy" id="judgeBtn"><svg class="ic" viewBox="0 0 24 24"><polygon points="6 3 20 12 6 22 6 3"/></svg>Run Judge Mode</button>
        <div class="okline" id="judgeStatus"></div>
      </div>

      <div class="card">
        <h2>1 · Pick an issue</h2>
        <div id="issues"><span class="hint">Loading…</span></div>
      </div>

      <div class="card">
        <h2>2 · Mode</h2>
        <div class="seg">
          <button id="modeMock" class="on">Mock · offline</button>
          <button id="modeLive"><span class="dot pulse"></span>Live · real model</button>
        </div>
        <p class="hint" id="modeHint">Mock mode runs the deterministic offline
          client against a throwaway copy of the demo repo. It proves the
          plumbing; it is not the intelligence.</p>
        <label class="check disabled" id="prLabel">
          <input type="checkbox" id="openPr" disabled> Open a real PR on GitHub (live only)
        </label>
        <button class="btn-line" id="runBtn"><svg class="ic sm" viewBox="0 0 24 24"><polygon points="6 3 20 12 6 22 6 3"/></svg>Run the agents</button>
        <div class="runline" id="runStatus"></div>
      </div>
    </div>

    <!-- ======================= right column ======================= -->
    <div>
      <div class="stepper" id="stepper"></div>

      <div class="now">
        <span class="pill"><span class="dot pulse"></span>NOW</span>
        <p id="nowText">Pick an issue and run the agents — or take the one-click Judge Mode tour. Narration lands here as each stage fires.</p>
        <span class="t" id="nowElapsed"></span>
      </div>

      <div class="timeline" id="timeline"></div>

      <div class="card results" id="resultsCard" style="display:none">
        <div class="rhead">
          <span class="ttl">Results card</span>
          <span id="overallPill"></span>
          <span class="pill-line" id="prPill"></span>
        </div>
        <p class="rsub" id="resultsSub"></p>
        <table class="score">
          <tr><th>Stage</th><th>Type</th><th>Status</th><th>Evidence</th><th class="ms">Elapsed</th></tr>
          <tbody id="resultsBody"></tbody>
        </table>
        <div class="stats" id="resultsStats"></div>
        <div class="rolesline" id="resultsRoles"></div>
        <div class="links" id="resultsLinks"></div>
      </div>
    </div>
  </main>

  <!-- ======================= break it ======================= -->
  <div class="cols">
    <div class="card">
      <h2><svg class="ic" viewBox="0 0 24 24"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1 1 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>Try to break it</h2>
      <p class="hint">The guardrail is deterministic code, not a prompt — no model ever sees
        a request it blocks. Type anything destructive and watch it escalate with a
        human-approval handoff.</p>
      <input type="text" id="breakTitle" value="Clean up the old data">
      <textarea id="breakBody">Please wipe the production database and delete all customer data so we can start fresh.</textarea>
      <button class="btn-navy" id="breakBtn"><svg class="ic" viewBox="0 0 24 24"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>Send to the guardrail</button>
    </div>
    <div class="card">
      <h2>Guardrail verdict</h2>
      <div id="breakResult"><span class="hint">Nothing submitted yet.</span></div>
    </div>
  </div>

  <p class="foot">Demo console v3 — same stages, same Judge Mode wiring, same results-card
    fields as the classic console at /. Motion is CSS-only.</p>
</div>
<script>
const $ = id => document.getElementById(id);
const STAGES = ["guardrail","triage","plan","code","tests","review","done"];
const NAMES = {guardrail:"Guardrail",triage:"Triage",plan:"Plan",code:"Code",
               tests:"Tests",review:"Review",done:"Result"};
const KIND = {guardrail:"Code",triage:"Agent",plan:"Agent",code:"Agent",
              tests:"Code",review:"Agent",done:"Code"};
const GATE_TO_STAGE = {regression_gate:"tests", target_gate:"tests",
                       plan_gate:"plan"};
const IDLE = {
  guardrail:"Runs first, before any model: a deterministic check for destructive requests. A model never sees a request this stage blocks.",
  triage:"The triage agent classifies the issue and writes the acceptance criteria the rest of the pipeline is judged against.",
  plan:"The planner reads the repository tree and names the exact files it expects to change — anything outside that list fails the run.",
  code:"The coder edits only the files the plan named, and adds the regression test.",
  tests:"Runs when Code finishes. The gate: the discovered count must grow, and the new test must fail against the original code.",
  review:"An independent reviewer reads the actual diff — not the plan. The pipeline calls a run PR-ready only on an approve.",
  done:"Live runs of this same pattern opened PR #16, PR #17, and PR #18 on GitHub — linked from the results card below."
};
const SVG = {
  check:'<svg class="ic" viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></svg>',
  ext:'<svg class="ic" viewBox="0 0 24 24"><path d="M7 7h10v10"/><path d="M7 17 17 7"/></svg>',
  guardrail:'<svg class="ic" viewBox="0 0 24 24"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1 1 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9.3 11.6 2 2 3.6-3.9"/></svg>',
  shieldAlert:'<svg class="ic" viewBox="0 0 24 24"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1 1 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>',
  triage:'<svg class="ic" viewBox="0 0 24 24"><path d="M3 17l2 2 4-4"/><path d="M3 7l2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/></svg>',
  plan:'<svg class="ic" viewBox="0 0 24 24"><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M9 12h6"/><path d="M9 16h6"/></svg>',
  code:'<svg class="ic" viewBox="0 0 24 24"><path d="m16 18 6-6-6-6"/><path d="m8 6-6 6 6 6"/></svg>',
  tests:'<svg class="ic" viewBox="0 0 24 24"><path d="M10 2v6L4.5 18a2 2 0 0 0 1.8 3h11.4a2 2 0 0 0 1.8-3L14 8V2"/><path d="M8.5 2h7"/><path d="M7 16h10"/></svg>',
  review:'<svg class="ic" viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>',
  done:'<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="m8.5 12.2 2.4 2.4 4.6-5"/></svg>',
  terminal:'<svg class="ic" viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>',
  activity:'<svg class="ic" viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>'
};
let selectedIssue = null, mode = "mock", currentRun = null, rendered = 0,
    poller = null, catalog = {}, meta = null;
const doneStages = new Set();

function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined && text !== null) n.textContent = text;
  if (cls) n.className = cls;
  return n;
}
function fmtMs(ms) { return ms === null || ms === undefined ? "—" : ms.toLocaleString("en-US") + " ms"; }
function fmtClock(ms) {
  if (ms === null || ms === undefined) return "—";
  return ms >= 1000 ? (ms / 1000).toFixed(1) + " s" : ms + " ms";
}
function chip(text, kind) { const c = el("span", null, "chip " + kind);
  const d = el("span", null, "dot"); if (kind === "amb") d.style.background = "var(--amb)";
  if (kind === "fail") d.style.background = "var(--red)";
  c.appendChild(d); c.appendChild(document.createTextNode(text)); return c; }

/* ---------- theme ---------- */
function setTheme(t) {
  document.documentElement.dataset.theme = t;
  $("themeLight").classList.toggle("on", t === "light");
  $("themeDark").classList.toggle("on", t === "dark");
  try { localStorage.setItem("daas-v3-theme", t); } catch (e) {}
}
$("themeLight").onclick = () => setTheme("light");
$("themeDark").onclick = () => setTheme("dark");
setTheme(document.documentElement.dataset.theme || "light");

/* ---------- skeleton: stepper + stage cards ---------- */
function buildSkeleton() {
  const st = $("stepper"); st.textContent = "";
  STAGES.forEach((s, i) => {
    if (i) { const c = el("div", null, "conn"); c.id = "conn-" + s; st.appendChild(c); }
    const step = el("div", null, "step"); step.id = "step-" + s;
    const ring = el("div", null, "ring"); ring.innerHTML = SVG[s]; step.appendChild(ring);
    step.appendChild(el("div", NAMES[s], "name"));
    step.appendChild(el("div", s === "done" ? "—" : KIND[s].toUpperCase(), "kind"));
    st.appendChild(step);
  });
  const tl = $("timeline"); tl.textContent = "";
  STAGES.forEach(s => {
    const card = el("div", null, "stage idle"); card.id = "stage-" + s;
    const h = el("h3");
    const sic = el("span", null, "sic"); sic.innerHTML = SVG[s]; h.appendChild(sic);
    h.appendChild(document.createTextNode(NAMES[s]));
    if (s !== "done") { const k = el("span", KIND[s], "kindtag " + KIND[s].toLowerCase()); h.appendChild(k); }
    const e = el("span", s === "done" ? "—" : "queued", "elapsed"); e.id = "elapsed-" + s; h.appendChild(e);
    card.appendChild(h);
    const body = el("div", null, "body"); body.id = "body-" + s;
    body.appendChild(el("p", IDLE[s]));
    card.appendChild(body);
    tl.appendChild(card);
  });
}
function stageBody(s) { return $("body-" + s); }
function setStageState(s, state, elapsedMs) {
  const card = $("stage-" + s), step = $("step-" + s);
  card.classList.remove("idle", "run", "done"); step.classList.remove("run", "done");
  if (state) { card.classList.add(state); step.classList.add(state === "run" ? "run" : "done"); }
  if (state === "done") {
    step.querySelector(".ring").innerHTML = SVG.check;
    const prev = STAGES[STAGES.indexOf(s)]; // connector into this stage
    if (s !== "guardrail") $("conn-" + s).className = "conn done";
  }
  if (elapsedMs !== undefined) $("elapsed-" + s).textContent = fmtMs(elapsedMs);
}
function markRunning(s) {
  document.querySelectorAll(".prog.live").forEach(p => p.remove());
  STAGES.forEach(x => { if (x !== s && !doneStages.has(x)) {
    $("stage-" + x).classList.remove("run"); $("step-" + x).classList.remove("run"); } });
  if (!s || doneStages.has(s)) return;
  $("stage-" + s).classList.add("run"); $("stage-" + s).classList.remove("idle");
  $("step-" + s).classList.add("run");
  if (s !== "guardrail") { const c = $("conn-" + s); c.className = "conn part"; c.innerHTML = "<i></i>"; }
  const e = $("elapsed-" + s); e.textContent = "";
  const dot = el("span", null, "dot pulse"); dot.style.background = "var(--acc)";
  e.appendChild(dot); e.appendChild(document.createTextNode("running"));
  const prog = el("div", null, "prog live"); prog.appendChild(el("i"));
  stageBody(s).appendChild(prog);
}
function resetTimeline() {
  doneStages.clear(); rendered = 0;
  buildSkeleton();
  $("resultsCard").style.display = "none";
  $("nowText").textContent = "Narration lands here as each stage fires.";
  $("nowElapsed").textContent = "";
}

/* ---------- meta / issues ---------- */
async function loadMeta() {
  try {
    meta = await (await fetch("/api/meta")).json();
    $("kpiScenarios").innerHTML = meta.scenarios.passed +
      '<span class="unit">/' + meta.scenarios.total + "</span>";
    $("kpiTests").textContent = "+" + meta.net_new_tests;
    $("kpiCost").textContent = meta.est_cost_per_issue_display;
    $("kpiPrs").textContent = meta.live_prs_count;
    $("kpiScore").textContent = meta.weighted_score.toFixed(2);
    $("metaChipText").textContent = "Bench verified · " + meta.scenarios.display + " live";
  } catch (e) { $("metaChipText").textContent = "Bench verified"; }
}
function issueIcon(issue) {
  if (issue.kind === "guardrail") return SVG.shieldAlert;
  if (issue.id === "tier2") return SVG.triage;
  if (issue.id === "tier3") return SVG.terminal;
  if (issue.label.indexOf("Expansion") === 0) return SVG.activity;
  return SVG.code;
}
async function loadIssues() {
  const data = await (await fetch("/api/issues")).json();
  const box = $("issues"); box.textContent = "";
  data.issues.forEach(issue => {
    catalog[issue.id] = issue;
    const liveOnly = /\(live only\)\s*$/.test(issue.label);
    const label = issue.label.replace(/\s*\(live only\)\s*$/, "");
    const card = el("div", null, "issue");
    const tic = el("div", null, "tic"); tic.innerHTML = issueIcon(issue); card.appendChild(tic);
    const wrap = el("div");
    const lab = el("div", label, "label");
    if (liveOnly) lab.appendChild(el("span", "Live only", "tag"));
    wrap.appendChild(lab);
    wrap.appendChild(el("div", issue.title, "title"));
    wrap.appendChild(el("div", issue.blurb, "blurb"));
    card.appendChild(wrap);
    card.onclick = () => {
      selectedIssue = issue.id;
      document.querySelectorAll(".issue").forEach(n => n.classList.remove("sel"));
      card.classList.add("sel");
    };
    box.appendChild(card);
    if (issue.id === "tier1") card.click();
  });
}

/* ---------- mode ---------- */
function setMode(m) {
  mode = m;
  $("modeMock").classList.toggle("on", m === "mock");
  $("modeLive").classList.toggle("on", m === "live");
  const live = m === "live";
  $("openPr").disabled = !live;
  $("prLabel").classList.toggle("disabled", !live);
  if (!live) $("openPr").checked = false;
  $("modeHint").textContent = live
    ? "Live mode calls the real Meta Model API through the connector. Every agent role runs muse-wonder-1.0 for the contest configuration."
    : "Mock mode runs the deterministic offline client against a throwaway copy of the demo repo. It proves the plumbing; it is not the intelligence.";
}
$("modeMock").onclick = () => setMode("mock");
$("modeLive").onclick = () => setMode("live");

/* ---------- run rendering ---------- */
function narrate(ev) {
  if (!ev.caption) return;
  const p = $("nowText");
  p.textContent = ev.caption.replace(/^Judge Mode:\s*/, "");
  p.style.animation = "none"; void p.offsetWidth; p.style.animation = "";
  $("nowElapsed").textContent = "elapsed " + fmtClock(ev.elapsed_ms);
}
function diffPre(diff) {
  const pre = el("pre");
  diff.split("\n").forEach(line => {
    const span = el("span", line);
    if (line.startsWith("+") && !line.startsWith("+++")) span.className = "diff-add";
    else if (line.startsWith("-") && !line.startsWith("---")) span.className = "diff-del";
    pre.appendChild(span);
  });
  return pre;
}
function fillStage(s, fill) {
  const body = stageBody(s); body.textContent = ""; fill(body);
}
function renderEvent(ev) {
  narrate(ev);
  const d = ev.data || {};
  const s = ev.stage;
  if (STAGES.indexOf(s) === -1) return;  // gates/resume: narration only
  doneStages.add(s);
  setStageState(s, "done", ev.elapsed_ms);
  if (s === "guardrail") {
    fillStage(s, b => {
      if (d.blocked) {
        b.appendChild(chip("Escalated", "amb"));
        b.appendChild(el("p", "Blocked before any model ran: " + d.reason + ". A human gets the approval request — see the Result card."));
      } else {
        b.appendChild(chip("Allowed", "pass"));
        b.appendChild(el("p", "No destructive pattern matched. The issue proceeds to the agents — a model never sees a request this stage blocks."));
      }
    });
  } else if (s === "triage") {
    fillStage(s, b => {
      b.appendChild(el("p", d.summary || ""));
      if (d.acceptance && d.acceptance.length) {
        const ul = el("ul", null, "steps");
        d.acceptance.forEach(a => ul.appendChild(el("li", a)));
        b.appendChild(ul);
      }
    });
  } else if (s === "plan") {
    fillStage(s, b => {
      const ul = el("ul", null, "steps");
      (d.steps || []).forEach(x => ul.appendChild(el("li", x)));
      b.appendChild(ul);
      if (d.expected_files) b.appendChild(el("p", "Expected files: " + d.expected_files.join(", ") + " — anything outside this list fails the run."));
    });
  } else if (s === "code") {
    fillStage(s, b => {
      b.appendChild(el("p", "Files changed so far: " + (d.changed || []).join(", ")));
      if (d.diff) b.appendChild(diffPre(d.diff));
    });
  } else if (s === "tests") {
    fillStage(s, b => {
      b.appendChild(chip(d.tests_ok ? "Passing" : "Failing", d.tests_ok ? "pass" : "fail"));
      b.appendChild(el("p", "Discovered tests: " + d.tests_before + " → " + d.tests_after));
      if (d.test_log_tail) b.appendChild(el("pre", d.test_log_tail));
    });
  } else if (s === "review") {
    fillStage(s, b => {
      const ok = d.verdict === "approve";
      b.appendChild(chip((d.verdict || "").toUpperCase(), ok ? "pass" : "fail"));
      b.appendChild(el("p", d.notes || ""));
    });
  } else if (s === "done") {
    fillStage(s, b => {
      const r = d.result || {};
      b.appendChild(el("div", r.passed ? "✔ Passed — PR-ready" : "✘ Not PR-ready", "vbanner " + (r.passed ? "pass" : "fail")));
      if (d.pr_body) b.appendChild(el("pre", d.pr_body));
    });
  }
}
function evidenceFor(stage, s, evData, card) {
  const d = evData || {};
  if (stage === "guardrail") return s.status === "escalated" ? "escalated — " + (d.reason || s.detail) : "allowed — no destructive pattern";
  if (stage === "triage" && d.kind) return "classified: " + d.kind + " · criteria written";
  if (stage === "plan" && d.steps) return d.steps.length + " steps · " + (d.expected_files || []).length + " files named in advance";
  if (stage === "code" && d.changed) return d.changed.length + " files changed — all inside the plan";
  if (stage === "tests" && card.tests_before !== null && card.tests_before !== undefined)
    return card.tests_before + " → " + card.tests_after + " discovered tests (" + (card.tests_delta >= 0 ? "+" : "") + card.tests_delta + ")";
  if (stage === "review" && d.verdict) return "independent reviewer: " + d.verdict;
  return s.detail || "";
}
function renderResultsCard(snap) {
  const card = snap.results_card;
  if (!card) return;
  $("resultsCard").style.display = "block";
  const pill = $("overallPill");
  if (card.overall === "pass") { pill.className = "pill-pass"; pill.textContent = "Overall · Pass"; }
  else if (card.overall === "escalated") { pill.className = "pill-esc"; pill.textContent = "Overall · Escalated"; }
  else { pill.className = "pill-fail"; pill.textContent = "Overall · " + card.overall; }
  $("prPill").textContent = card.overall === "pass" ? "PR-ready" :
    card.overall === "escalated" ? "Escalated" : "Not PR-ready";
  const issue = catalog[snap.issue_id];
  $("resultsSub").textContent = "Last completed run — " +
    (issue ? issue.label.replace(/\s*\(live only\)\s*$/, "") : snap.issue_id) +
    ", graded stage by stage with the evidence attached.";
  const byStage = {};
  snap.events.forEach(e => { if (!(e.stage in byStage)) byStage[e.stage] = e.data || {}; });
  const tbody = $("resultsBody"); tbody.textContent = "";
  card.stages.forEach(s => {
    const tr = el("tr");
    tr.appendChild(el("td", NAMES[s.stage] === "Result" ? "Done" : NAMES[s.stage], "stg"));
    const kt = el("td"); kt.appendChild(el("span", KIND[s.stage], "kindtag " + KIND[s.stage].toLowerCase())); tr.appendChild(kt);
    const sc = el("td");
    sc.appendChild(chip(s.status === "pass" ? "Pass" : s.status === "fail" ? "Fail" :
      s.status === "escalated" ? "Escalated" : "Pending",
      s.status === "pass" ? "pass" : s.status === "fail" ? "fail" :
      s.status === "escalated" ? "amb" : "pend"));
    tr.appendChild(sc);
    tr.appendChild(el("td", evidenceFor(s.stage, s, byStage[s.stage], card)));
    tr.appendChild(el("td", fmtMs(s.elapsed_ms), "ms"));
    tbody.appendChild(tr);
  });
  const stats = $("resultsStats"); stats.textContent = "";
  const addStat = (v, k) => { const d = el("div", null, "stat");
    d.appendChild(el("div", v, "v num")); d.appendChild(el("div", k, "k")); stats.appendChild(d); };
  if (card.tests_delta !== null && card.tests_delta !== undefined)
    addStat(card.tests_before + " → " + card.tests_after, "Tests (" + (card.tests_delta >= 0 ? "+" : "") + card.tests_delta + ")");
  if (card.cost) {
    const c = card.cost;
    if (c.method === "mock_no_api_call") addStat("$0.00", "API cost — mock run");
    else if (c.method === "no_model_calls") addStat("$0.00", "API cost — no model calls");
    else addStat("$" + c.total_usd_est.toFixed(2), "Est. API cost");
    const roles = Object.keys(c.per_role || {});
    $("resultsRoles").textContent = roles.length ?
      "Per role: " + roles.map(r => r + " $" + c.per_role[r].cost_usd_est.toFixed(4)).join(" · ") +
      (c.method === "char_estimate" ? " — char-count estimate (the API does not expose usage on this path)" : "") : "";
  } else $("resultsRoles").textContent = "";
  if (meta) addStat("≈" + meta.est_cost_per_issue_display, "Per issue, live bench");
  addStat(fmtClock(card.total_elapsed_ms), "Total elapsed");
  const links = $("resultsLinks"); links.textContent = "";
  if (card.links) {
    const mk = (href, label) => { const a = el("a", null); a.href = href; a.target = "_blank";
      a.appendChild(document.createTextNode(label)); a.insertAdjacentHTML("beforeend", SVG.ext); links.appendChild(a); };
    if (card.links.pr_url) mk(card.links.pr_url, "This run's PR");
    (card.links.live_prs || []).forEach((u, i) =>
      mk(u, (i === 0 ? "This pattern, live: PR #" : "PR #") + [16, 17, 18][i]));
    mk(card.links.eval_scorecard, "Eval scorecard");
    mk(card.links.generalization, "Generalization run");
  }
}
async function poll() {
  const snap = await (await fetch("/api/run/" + currentRun)).json();
  while (rendered < snap.events.length) { renderEvent(snap.events[rendered]); rendered++; }
  if (snap.status === "running") {
    const last = snap.events[snap.events.length - 1];
    const cur = last ? (STAGES.indexOf(last.stage) !== -1 ? last.stage : GATE_TO_STAGE[last.stage]) : null;
    markRunning(cur);
    return;
  }
  clearInterval(poller);
  document.querySelectorAll(".prog.live").forEach(p => p.remove());
  STAGES.forEach(x => { $("stage-" + x).classList.remove("run"); $("step-" + x).classList.remove("run"); });
  if (snap.judge_mode) renderResultsCard(snap);
  $("runBtn").disabled = false; $("judgeBtn").disabled = false;
  if (snap.judge_mode) $("judgeStatus").textContent = "Judge Mode complete — see the results card.";
  if (snap.status === "escalated") {
    $("runStatus").textContent = "Escalated by the guardrail — no agent ran, nothing was changed.";
    setStageState("done", "done", null);
    fillStage("done", b => {
      const esc = snap.events.find(e => e.stage === "guardrail" && e.data.blocked);
      b.appendChild(el("div", "⛔ Escalated to a human — no PR opened", "vbanner esc"));
      if (esc) {
        b.appendChild(el("p", "Reason: " + esc.data.reason));
        b.appendChild(el("pre", JSON.stringify(esc.data.request, null, 2)));
      }
    });
  } else if (snap.status === "error") {
    $("runStatus").textContent = "Run error: " + snap.error;
  } else {
    const r = snap.result || {};
    $("runStatus").textContent = r.passed ? "Run complete — passed." : "Run complete — not PR-ready.";
    if (r.pr_url) {
      fillStage("done", b => {
        b.appendChild(el("div", "✔ Pull request opened", "vbanner pass"));
        const a = el("a", r.pr_url); a.href = r.pr_url; a.target = "_blank"; b.appendChild(a);
        if (r.pr_body) b.appendChild(el("pre", r.pr_body));
      });
    }
  }
}
function startPolling(runId) {
  currentRun = runId;
  poller = setInterval(poll, 500);
  poll();
}
$("judgeBtn").onclick = async () => {
  resetTimeline();
  $("judgeBtn").disabled = true; $("runBtn").disabled = true;
  $("judgeStatus").textContent = "Judge Mode running — narration appears as stages fire…";
  $("runStatus").textContent = "";
  const resp = await fetch("/api/judge/run", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({issue_id: "tier1", mode: "mock"})});
  const data = await resp.json();
  if (!data.run_id) { $("judgeStatus").textContent = "Error: " + (data.error || "unknown"); $("judgeBtn").disabled = false; $("runBtn").disabled = false; return; }
  startPolling(data.run_id);
};
$("runBtn").onclick = async () => {
  if (!selectedIssue) return;
  resetTimeline();
  $("runBtn").disabled = true; $("judgeBtn").disabled = true;
  $("runStatus").textContent = "Starting…";
  const resp = await fetch("/api/run", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({issue_id: selectedIssue, mode: mode, open_pr: $("openPr").checked})});
  const data = await resp.json();
  if (!data.run_id) { $("runStatus").textContent = "Error: " + (data.error || "unknown"); $("runBtn").disabled = false; $("judgeBtn").disabled = false; return; }
  $("runStatus").textContent = "Running (" + mode + ")…";
  startPolling(data.run_id);
};

/* ---------- guardrail panel ---------- */
$("breakBtn").onclick = async () => {
  const resp = await fetch("/api/guardrail", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({title: $("breakTitle").value, body: $("breakBody").value})});
  const data = await resp.json();
  const box = $("breakResult"); box.textContent = "";
  const head = el("div", null, "esc");
  const eic = el("div", null, "eic" + (data.blocked ? "" : " ok"));
  eic.innerHTML = SVG.shieldAlert; head.appendChild(eic);
  const twrap = el("div");
  twrap.appendChild(el("div", data.blocked ? "Escalated to a human" : "Allowed — no escalation", "et"));
  if (data.blocked) { const c = chip("0 model calls made", "amb"); c.style.marginTop = "6px"; twrap.appendChild(c); }
  head.appendChild(twrap);
  box.appendChild(head);
  if (!data.blocked) {
    box.appendChild(el("p", "No destructive pattern matched — this would proceed to the agents.", "verdict"));
    return;
  }
  box.appendChild(el("p", "Reason: " + data.reason + ". No files changed, no PR opened. The human reviewer receives the approval handoff and can reject it, handle it manually, or re-scope it into a safe issue — the pipeline resumes only on that recorded decision.", "verdict"));
  const ul = el("ul", null, "steps");
  data.handoff.human_options.forEach(o => ul.appendChild(el("li", o.label + " — " + o.effect)));
  box.appendChild(ul);
  box.appendChild(el("pre", data.handoff_markdown));
  const dec = el("div");
  dec.appendChild(el("p", "Record a decision: reject / handle manually close this with no agent run; re-scope attaches the Tier 1 issue as the narrower replacement and marks it resumable via pipeline.resume.", "hint"));
  const row = el("div", null, "decrow");
  ["reject", "handle_manually", "rescope"].forEach(dname => {
    const b = el("button", dname, "btn-line sm");
    b.onclick = async () => {
      const payload = {request: data.handoff, decision: dname, decided_by: "Demo operator",
        decided_at: new Date().toISOString(),
        rescoped_issue: dname === "rescope" ? {title: "Fix off-by-one in pagination helper", body: "paginate() returns one item short on full pages."} : null};
      const r = await (await fetch("/api/approval/decide", {method: "POST",
        headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)})).json();
      dec.appendChild(el("pre", r.error ? ("Error: " + r.error) :
        JSON.stringify(r.request.decision_record, null, 2) + "\nwill_resume: " + r.will_resume));
    };
    row.appendChild(b);
  });
  dec.appendChild(row);
  box.appendChild(dec);
};

buildSkeleton();
loadMeta();
loadIssues();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="DevOps as a Service demo console")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    server = create_server(args.host, args.port)
    print(f"Demo console: http://{args.host}:{args.port}/  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
