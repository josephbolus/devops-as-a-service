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
ISSUE_CATALOG = [
    ("tier1", "Tier 1 — Bug fix", "paginate() returns one item short on full pages."),
    ("tier2", "Tier 2 — Feature", "Add retry with backoff to the HTTP client wrapper."),
    ("tier3", "Tier 3 — Feature", "Make the CLI output machine-readable (--json)."),
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
