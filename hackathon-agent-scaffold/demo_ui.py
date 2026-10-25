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
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import run_pr  # noqa: E402
from daas import approval, guardrail, pipeline  # noqa: E402
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


# ---------------------------------------------------------------- runs

_RUNS = {}
_RUNS_LOCK = threading.Lock()


def _new_run(issue_id, mode, open_pr):
    run_id = uuid.uuid4().hex[:12]
    record = {"id": run_id, "issue_id": issue_id, "mode": mode,
              "open_pr": open_pr, "status": "running", "events": [],
              "result": None, "error": None, "lock": threading.Lock()}
    with _RUNS_LOCK:
        _RUNS[run_id] = record
    return record


def get_run(run_id):
    with _RUNS_LOCK:
        return _RUNS.get(run_id)


def _collector(record):
    def collect(event):
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


def start_run(issue_id, mode, open_pr):
    record = _new_run(issue_id, mode, open_pr)
    threading.Thread(target=_execute_run, args=(record,), daemon=True).start()
    return record


def run_snapshot(record):
    with record["lock"]:
        events = list(record["events"])
    return {"id": record["id"], "status": record["status"],
            "issue_id": record["issue_id"], "mode": record["mode"],
            "open_pr": record["open_pr"], "events": events,
            "result": record["result"], "error": record["error"]}


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
        if self.path == "/api/run":
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
            record = start_run(issue_id, mode, open_pr)
            self._send_json(200, {"run_id": record["id"]})
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

async function poll() {
  const snap = await (await fetch("/api/run/" + currentRun)).json();
  while (rendered < snap.events.length) { renderEvent(snap.events[rendered]); rendered++; }
  if (snap.status === "running") return;
  clearInterval(poller);
  $("runBtn").disabled = false;
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
