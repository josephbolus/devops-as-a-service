"""The Approve-to-Pay approval console — the screen the human gate sees.

A small local web UI (Python standard library only, no build step) that
makes the pipeline legible stage by stage:

    guardrail verdict (deterministic code, with its reason)
    -> PayPal order, real order ID, state UNCAPTURED
    -> payer approval (PayPal's step, visually distinct)
    -> console approval (Approve-to-Pay's human gate — Approve / Deny)
    -> capture -> COMPLETED, the captured order as the receipt
       or, on Deny: capture never called, $0 moved, log entry as proof

The console *consumes* the pipeline — it never reimplements verdicts.
An interactive run calls ``pipeline.run_job`` with the pipeline's
``decide`` hook: the run pauses inside the hook, order already created
and still UNCAPTURED, until the approver clicks. The batch results
panel and the "run task set" action shell out to ``run_tasks.py``
exactly as a judge would run it from the CLI.

Mode follows the PayPal client: with PAYPAL_CLIENT_ID /
PAYPAL_CLIENT_SECRET set, runs hit the real PayPal sandbox with zero UI
changes; without them the fixture mock runs and the page is labeled
SANDBOX-FIXTURE in the header, on every session, and in every report.

Run it (from the approve-to-pay/ directory):

    python3 run_console.py            # http://127.0.0.1:8765
    python3 run_console.py --port 9000
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import pipeline
from .decision_log import DecisionLog
from .paypal_client import from_env

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG = ROOT / "decision-log.jsonl"
REPORT_PATH = ROOT / "results" / "latest-report.json"
DECIDE_TIMEOUT_SECONDS = 900  # fail-safe: no answer in 15 min -> deny


def mode_info() -> dict:
    """Describe the PayPal mode the next run will use, for labeling."""
    client = from_env()
    if client.mode == "mock":
        return {"mode": "mock",
                "label": "SANDBOX-FIXTURE",
                "detail": "fixture mock — no PayPal credentials configured"}
    if os.environ.get("PAYPAL_ENV") == "live":
        return {"mode": "live", "label": "LIVE — PayPal production",
                "detail": "real PayPal API (PAYPAL_ENV=live)"}
    return {"mode": "live", "label": "LIVE — PayPal sandbox",
            "detail": "real PayPal sandbox API"}


def public_job(job: dict) -> dict:
    """The job fields the console displays (never the whole frozen file)."""
    return {k: job.get(k) for k in (
        "id", "title", "item", "merchant", "category", "quoted_price",
        "checkout_price", "budget_cap", "approver_decision",
        "expected_outcome", "expected_reason")}


class ConsoleState:
    """One interactive session at a time; batch runs are stateless."""

    def __init__(self, task_set: dict, log_path: Path):
        self.task_set = task_set
        self.log_path = Path(log_path)
        self.decide_timeout = DECIDE_TIMEOUT_SECONDS
        self._lock = threading.Lock()
        self._decision_event = threading.Event()
        self._session: dict = {"status": "idle"}

    # -- session lifecycle ---------------------------------------------
    def start_run(self, job: dict) -> tuple[bool, str]:
        with self._lock:
            if self._session.get("status") in ("running", "awaiting_console"):
                return False, "a run is already in progress"
            self._decision_event.clear()
            self._session = {
                "status": "running",
                "stage": "guardrail",
                "job": public_job(job),
                "mode": mode_info(),
                "order_id": None,
                "order_status": None,
                "payer_action_url": None,
                "decision": None,
                "decision_note": None,
                "entry": None,
                "error": None,
            }
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return True, "started"

    def _run(self, job: dict) -> None:
        client = from_env()
        log = DecisionLog(self.log_path)
        run_id = uuid.uuid4().hex[:12]

        def decide(job_: dict, order) -> str:
            # The pipeline pauses here: the order exists, UNCAPTURED,
            # payer approval already recorded — the human gate is open.
            with self._lock:
                self._session.update(
                    status="awaiting_console", stage="console",
                    order_id=order.order_id, order_status=order.status,
                    payer_action_url=order.payer_action_url)
            answered = self._decision_event.wait(self.decide_timeout)
            with self._lock:
                decision = self._session.get("decision") or "deny"
                if not answered:
                    decision = "deny"  # fail-safe: silence never captures
                    self._session["decision_note"] = (
                        "no decision within "
                        f"{self.decide_timeout // 60} min — treated as deny "
                        "(fail-safe: capture requires an explicit yes)")
                self._session.update(status="running", stage="capture")
            return decision

        try:
            entry = pipeline.run_job(job, self.task_set["policy"], client,
                                     log, run_id, decide=decide)
            with self._lock:
                self._session.update(status="done", stage="done",
                                     entry=entry)
        except Exception as exc:  # surface, never swallow
            with self._lock:
                self._session.update(status="error", stage="error",
                                     error=f"{type(exc).__name__}: {exc}")

    def decide(self, decision: str) -> tuple[bool, str]:
        if decision not in ("approve", "deny"):
            return False, "decision must be 'approve' or 'deny'"
        with self._lock:
            if self._session.get("status") != "awaiting_console":
                return False, "no run is waiting for a decision"
            self._session["decision"] = decision
        self._decision_event.set()
        return True, "recorded"

    def session(self) -> dict:
        with self._lock:
            return dict(self._session)

    # -- read models -----------------------------------------------------
    def report(self) -> dict | None:
        if REPORT_PATH.exists():
            return json.loads(REPORT_PATH.read_text())
        return None

    def log_tail(self, limit: int) -> list[dict]:
        entries = DecisionLog(self.log_path).read_all()
        return list(reversed(entries[-limit:]))

    def run_task_set(self) -> dict:
        """Run the frozen set exactly as the CLI does, then re-read the
        report the runner wrote. Credentials, if set, flow through the
        environment to the subprocess unchanged."""
        proc = subprocess.run(
            [sys.executable, "run_tasks.py"], cwd=ROOT,
            capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            raise RuntimeError(
                f"run_tasks.py failed: {proc.stderr.strip()[-500:]}")
        return self.report() or {}


def _load_task_set() -> dict:
    # Reuse the runner's checksum verification: the console refuses to
    # present a modified frozen set, same as the CLI.
    from . import cli
    return cli.verify_frozen_set()


class _Handler(BaseHTTPRequestHandler):
    server: "ConsoleServer"

    def log_message(self, *args):  # keep the console quiet
        pass

    # -- helpers ---------------------------------------------------------
    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length))

    # -- routes ------------------------------------------------------------
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        state = self.server.state
        if path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/jobs":
            self._send_json({
                "version": state.task_set["version"],
                "policy": state.task_set["policy"],
                "jobs": [public_job(j) for j in state.task_set["jobs"]],
                "mode": mode_info(),
            })
        elif path == "/api/session":
            self._send_json(state.session())
        elif path == "/api/report":
            self._send_json({"report": state.report()})
        elif path == "/api/log":
            qs = parse_qs(urlparse(self.path).query)
            limit = min(int(qs.get("limit", ["30"])[0]), 200)
            self._send_json({"entries": state.log_tail(limit)})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        state = self.server.state
        try:
            body = self._read_json()
        except (ValueError, json.JSONDecodeError):
            return self._send_json({"error": "invalid JSON body"}, 400)
        if path == "/api/run":
            job = next((j for j in state.task_set["jobs"]
                        if j["id"] == body.get("job_id")), None)
            if job is None:
                return self._send_json({"error": "unknown job_id"}, 404)
            ok, msg = state.start_run(job)
            self._send_json({"ok": ok, "message": msg},
                            200 if ok else 409)
        elif path == "/api/decide":
            ok, msg = state.decide(str(body.get("decision", "")))
            self._send_json({"ok": ok, "message": msg},
                            200 if ok else 409)
        elif path == "/api/run-all":
            try:
                report = state.run_task_set()
            except Exception as exc:
                return self._send_json(
                    {"error": f"{type(exc).__name__}: {exc}"}, 500)
            self._send_json({"report": report})
        else:
            self._send_json({"error": "not found"}, 404)


class ConsoleServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, state: ConsoleState):
        self.state = state
        super().__init__(address, _Handler)


def make_server(host: str = "127.0.0.1", port: int = 8765,
                log_path: Path = DEFAULT_LOG) -> ConsoleServer:
    state = ConsoleState(_load_task_set(), Path(log_path))
    return ConsoleServer((host, port), state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Approve-to-Pay approval console (local web UI)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--log", default=str(DEFAULT_LOG),
                        help="decision log path (default: decision-log.jsonl)")
    args = parser.parse_args(argv)
    server = make_server(args.host, args.port, Path(args.log))
    info = mode_info()
    print(f"Approve-to-Pay console: http://{args.host}:{args.port}")
    print(f"PayPal mode: {info['label']} — {info['detail']}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


# ---------------------------------------------------------------------------
# The page. One self-contained document: no build step, no external assets
# (icons are inline Lucide-style stroke SVGs), so a judge can open it the
# moment the server starts, online or off.
# ---------------------------------------------------------------------------

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Approve-to-Pay — approval console</title>
<style>
  :root{
    --bg:#f3f4f8; --card:#ffffff; --line:#e2e5ef; --line-soft:#eceef5;
    --ink:#1b2140; --body:#333a56; --muted:#5b6178;
    --accent:#4653c8; --accent-deep:#37439f; --accent-soft:#eef0fc;
    --navy:#232c5c; --paypal:#2c4a7c; --paypal-soft:#e9effa;
    --ok:#17724a; --ok-soft:#e7f4ee;
    --bad:#b23a2e; --bad-soft:#fbecea;
    --warn-bg:#fdf6e0; --warn-line:#e8d48b; --warn-text:#7c5a00;
    --radius:14px;
    --shadow:0 1px 2px rgba(27,33,64,.05), 0 4px 18px rgba(27,33,64,.05);
  }
  *{box-sizing:border-box}
  html,body{margin:0;padding:0}
  body{
    background:var(--bg); color:var(--body);
    font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
      "Helvetica Neue",Arial,sans-serif;
    font-size:15px; line-height:1.55;
    -webkit-font-smoothing:antialiased;
  }
  .wrap{max-width:1180px;margin:0 auto;padding:28px 22px 56px}

  /* header */
  header.top{display:flex;align-items:flex-start;gap:16px;flex-wrap:wrap;
    margin-bottom:22px}
  .brand{display:flex;gap:13px;align-items:center;margin-right:auto}
  .brand .mark{width:42px;height:42px;border-radius:11px;background:var(--accent-soft);
    color:var(--accent);display:flex;align-items:center;justify-content:center;flex:none}
  .brand h1{font-size:21px;line-height:1.15;margin:0;color:var(--ink);
    font-weight:650;letter-spacing:-.02em}
  .brand p{margin:2px 0 0;color:var(--muted);font-size:13px}
  .mode-badge{border:1px solid var(--warn-line);background:var(--warn-bg);
    color:var(--warn-text);border-radius:10px;padding:8px 13px;font-size:12.5px;
    line-height:1.35;text-align:right}
  .mode-badge b{display:block;font-size:13px;letter-spacing:.04em}
  .mode-badge.live{border-color:#bcd6c6;background:var(--ok-soft);color:var(--ok)}
  .mode-badge .sub{opacity:.85}

  /* layout */
  .grid{display:grid;grid-template-columns:minmax(0,1fr) 372px;gap:20px;
    align-items:start}
  @media (max-width:960px){.grid{grid-template-columns:1fr}}
  .col{display:flex;flex-direction:column;gap:20px;min-width:0}
  .card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
    box-shadow:var(--shadow);padding:22px 24px}
  .card h2{font-size:15.5px;margin:0 0 4px;color:var(--ink);font-weight:650;
    letter-spacing:-.01em;display:flex;align-items:center;gap:9px}
  .card h2 svg{color:var(--accent)}
  .card .sub{color:var(--muted);font-size:13px;margin:0 0 14px}
  .card-head{display:flex;align-items:flex-start;gap:12px}
  .card-head .grow{flex:1}

  button{font:inherit;cursor:pointer;border-radius:9px;border:1px solid var(--line);
    background:#fff;color:var(--ink);padding:8px 15px;font-size:13.5px;font-weight:550;
    transition:background .15s,border-color .15s,transform .1s}
  button:hover{border-color:#c9cede;background:#fafbfe}
  button:active{transform:translateY(1px)}
  button:disabled{opacity:.45;cursor:not-allowed;transform:none}
  button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
  button.primary:hover{background:var(--accent-deep);border-color:var(--accent-deep)}
  button.approve{background:var(--accent);border-color:var(--accent);color:#fff;
    padding:11px 26px;font-size:14.5px}
  button.approve:hover{background:var(--accent-deep);border-color:var(--accent-deep)}
  button.deny{background:#fff;border-color:#e0b6b0;color:var(--bad);
    padding:11px 26px;font-size:14.5px}
  button.deny:hover{background:var(--bad-soft);border-color:var(--bad)}

  /* job list */
  .jobs{display:flex;flex-direction:column}
  .job{display:flex;gap:12px;align-items:center;padding:10px 10px;
    border-top:1px solid var(--line-soft);cursor:pointer;border-radius:8px;
    transition:background .12s}
  .job:first-child{border-top:none}
  .job:hover{background:#f7f8fc}
  .job.selected{background:var(--accent-soft)}
  .job .jid{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;
    color:var(--muted);flex:none;width:58px}
  .job .jmain{flex:1;min-width:0}
  .job .jtitle{color:var(--ink);font-size:14px;font-weight:550;white-space:nowrap;
    overflow:hidden;text-overflow:ellipsis}
  .job .jitem{color:var(--muted);font-size:12.5px;white-space:nowrap;overflow:hidden;
    text-overflow:ellipsis}
  .job .jamt{font-weight:600;color:var(--ink);font-size:14px;flex:none}
  .tag{flex:none;font-size:11px;font-weight:600;letter-spacing:.03em;padding:2.5px 8px;
    border-radius:99px;border:1px solid var(--line);color:var(--muted);background:#fff}
  .tag.exp-capture{color:var(--ok);border-color:#bcd6c6;background:var(--ok-soft)}
  .tag.exp-guard{color:var(--paypal);border-color:#c3d2ee;background:var(--paypal-soft)}
  .tag.exp-approver{color:var(--warn-text);border-color:var(--warn-line);background:var(--warn-bg)}

  /* stage stepper */
  .run-head{display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap}
  .run-head .grow{flex:1;min-width:220px}
  .run-title{font-size:17.5px;color:var(--ink);font-weight:650;letter-spacing:-.015em;
    margin:0}
  .run-meta{color:var(--muted);font-size:13px;margin:3px 0 0}
  .run-amount{text-align:right}
  .run-amount .amt{font-size:24px;font-weight:680;color:var(--ink);letter-spacing:-.02em}
  .run-amount .cap{color:var(--muted);font-size:12px}
  .idle-note{color:var(--muted);font-size:14px;border:1px dashed var(--line);
    border-radius:10px;padding:18px;text-align:center;margin-top:6px}

  .steps{margin-top:18px;display:flex;flex-direction:column}
  .step{display:flex;gap:14px;position:relative;padding:0 0 20px 0}
  .step:last-child{padding-bottom:2px}
  .step::before{content:"";position:absolute;left:15px;top:34px;bottom:2px;width:2px;
    background:var(--line-soft);border-radius:2px}
  .step:last-child::before{display:none}
  .step .dot{width:32px;height:32px;border-radius:50%;flex:none;z-index:1;
    border:1.5px solid var(--line);background:#fff;color:#9aa0b5;
    display:flex;align-items:center;justify-content:center;
    transition:border-color .3s,color .3s,background .3s}
  .step.active .dot{border-color:var(--accent);color:var(--accent)}
  .step.active .dot::after{content:"";position:absolute;width:32px;height:32px;
    border-radius:50%;border:1.5px solid var(--accent);opacity:0;
    animation:ping 1.6s ease-out infinite}
  @keyframes ping{0%{transform:scale(1);opacity:.45}80%,100%{transform:scale(1.45);opacity:0}}
  .step.done .dot{border-color:var(--ok);background:var(--ok-soft);color:var(--ok)}
  .step.blocked .dot{border-color:var(--bad);background:var(--bad-soft);color:var(--bad)}
  .step .sbody{flex:1;min-width:0;padding-top:3px}
  .step .slabel{color:var(--ink);font-weight:600;font-size:14.5px;display:flex;
    align-items:center;gap:9px;flex-wrap:wrap}
  .step.pending .slabel{color:#8a90a6}
  .step .sdesc{color:var(--muted);font-size:13px;margin-top:1px}
  .step.pending .sdesc{color:#a3a8ba}
  .chip{font-size:11px;font-weight:650;letter-spacing:.045em;padding:2.5px 8px;
    border-radius:99px;text-transform:uppercase}
  .chip.code{background:var(--accent-soft);color:var(--accent-deep)}
  .chip.paypal{background:var(--paypal-soft);color:var(--paypal)}
  .chip.gate{background:var(--navy);color:#fff}
  .sresult{margin-top:7px;font-size:13.5px;animation:rise .35s ease both}
  @keyframes rise{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
  .mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px}
  .pill{display:inline-flex;align-items:center;gap:6px;font-weight:650;font-size:12px;
    letter-spacing:.05em;padding:3.5px 10px;border-radius:99px;
    transition:background .45s,color .45s,border-color .45s}
  .pill.uncaptured{background:var(--warn-bg);color:var(--warn-text);
    border:1px solid var(--warn-line)}
  .pill.completed{background:var(--ok-soft);color:var(--ok);border:1px solid #bcd6c6}
  .pill.never{background:var(--bad-soft);color:var(--bad);border:1px solid #efc4be}
  .pill.plain{background:#f1f2f7;color:var(--muted);border:1px solid var(--line)}
  .reason{color:var(--bad);font-weight:600}
  .ok-text{color:var(--ok);font-weight:600}

  .uncaptured-banner{margin-top:10px;border:1px solid var(--warn-line);
    background:var(--warn-bg);color:var(--warn-text);border-radius:10px;
    padding:11px 14px;font-size:13.5px;display:flex;gap:10px;align-items:center;
    animation:breathe 2.6s ease-in-out infinite}
  @keyframes breathe{0%,100%{box-shadow:0 0 0 0 rgba(214,178,60,0)}
    50%{box-shadow:0 0 0 4px rgba(214,178,60,.14)}}
  .gate-actions{margin-top:13px;display:flex;gap:11px;flex-wrap:wrap;align-items:center}
  .gate-actions .hint{color:var(--muted);font-size:12.5px}

  .receipt{margin-top:10px;border:1px solid #bcd6c6;background:var(--ok-soft);
    border-radius:10px;padding:12px 15px;font-size:13.5px;color:var(--body);
    animation:rise .4s ease both}
  .receipt b{color:var(--ok)}
  .zero{margin-top:10px;border:1px solid #efc4be;background:var(--bad-soft);
    border-radius:10px;padding:12px 15px;font-size:13.5px;animation:rise .4s ease both}
  .zero b{color:var(--bad)}
  .proof{margin-top:9px;background:#f7f8fc;border:1px solid var(--line-soft);
    border-radius:8px;padding:9px 12px;overflow-x:auto;white-space:pre;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;
    color:var(--body)}

  /* results */
  .stats{display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-bottom:6px}
  .stat{border:1px solid var(--line-soft);border-radius:10px;padding:11px 13px;
    background:#fcfcfe}
  .stat .n{font-size:21px;font-weight:680;color:var(--ink);letter-spacing:-.02em}
  .stat .l{color:var(--muted);font-size:12px;margin-top:1px}
  .stat.hero{grid-column:1/-1;background:var(--ok-soft);border-color:#bcd6c6}
  .stat.hero .n{color:var(--ok)}
  .kv{display:flex;justify-content:space-between;gap:10px;padding:6.5px 0;
    border-top:1px solid var(--line-soft);font-size:13.5px}
  .kv:first-of-type{border-top:none}
  .kv .k{color:var(--muted)}
  .kv .v{color:var(--ink);font-weight:580;text-align:right}
  .misses{font-size:13px;margin-top:4px}
  .misses .none{color:var(--ok);font-weight:580}
  .misses .some{color:var(--bad);font-weight:580}

  /* decision log */
  .loglist{display:flex;flex-direction:column;max-height:520px;overflow:auto}
  .lrow{border-top:1px solid var(--line-soft);padding:9px 2px;font-size:12.5px}
  .lrow:first-child{border-top:none}
  .lrow .ltop{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
  .lrow .ltime{color:var(--muted);font-size:11.5px;margin-left:auto}
  .lrow .ldet{color:var(--muted);margin-top:2px}
  .lrow .ldet b{color:var(--body);font-weight:580}
  footer{margin-top:26px;color:var(--muted);font-size:12.5px;text-align:center}
  .err{background:var(--bad-soft);border:1px solid #efc4be;color:var(--bad);
    border-radius:10px;padding:11px 14px;font-size:13.5px;margin-top:12px;display:none}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="brand">
      <div class="mark" id="brand-icon"></div>
      <div>
        <h1>Approve-to-Pay</h1>
        <p>Agentic purchasing — agents propose, a human authorizes, PayPal captures.</p>
      </div>
    </div>
    <div class="mode-badge" id="mode-badge">…</div>
  </header>

  <div class="grid">
    <div class="col">
      <!-- live run -->
      <section class="card" id="run-card">
        <div class="run-head">
          <div class="grow">
            <p class="run-title" id="run-title">No run yet</p>
            <p class="run-meta" id="run-meta">Pick a purchasing job below and run it.
              The guardrail decides in code; if an order is created it sits
              UNCAPTURED until you decide here.</p>
          </div>
          <div class="run-amount" id="run-amount" style="display:none">
            <div class="amt" id="run-amt"></div>
            <div class="cap" id="run-cap"></div>
          </div>
        </div>
        <div class="err" id="run-error"></div>
        <div class="steps" id="steps" style="display:none"></div>
        <div class="idle-note" id="idle-note">The five stages of a run — guardrail,
          order, payer approval, your approval, capture — will appear here.</div>
      </section>

      <!-- jobs -->
      <section class="card">
        <div class="card-head">
          <div class="grow">
            <h2><span data-icon="list"></span>Purchasing jobs</h2>
            <p class="sub" id="jobs-sub">The frozen task set — defined before the
              runner was wired, checksum-pinned. Expected outcomes shown; the
              console reports what actually happens, misses included.</p>
          </div>
          <button class="primary" id="run-job-btn" disabled>Run selected job</button>
        </div>
        <div class="jobs" id="jobs"></div>
      </section>
    </div>

    <div class="col">
      <!-- results -->
      <section class="card">
        <div class="card-head">
          <div class="grow">
            <h2><span data-icon="chart"></span>Task-set results</h2>
            <p class="sub" id="report-sub">The frozen 20-job set, measured — not modeled.</p>
          </div>
          <button id="run-all-btn">Run all 20 jobs</button>
        </div>
        <div id="report-body"><p class="sub">No batch run recorded yet.</p></div>
      </section>

      <!-- decision log -->
      <section class="card">
        <h2><span data-icon="file"></span>Decision log</h2>
        <p class="sub">Append-only audit trail (decision-log.jsonl). Every blocked
          purchase carries its own proof: <span class="mono">capture_called: false</span>.</p>
        <div class="loglist" id="loglist"></div>
      </section>
    </div>
  </div>

  <footer>Approve-to-Pay · built on the DevOps as a Service guardrail pattern ·
    the verdict path is deterministic code — no model judgment ·
    PayPal order state is the ground truth.</footer>
</div>

<script>
"use strict";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s)
  .replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const money = (v) => "$" + Number(v).toFixed(2);

const ICONS = {
  shield: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg>',
  list: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/></svg>',
  chart: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M7 14v3M12 10v7M17 6v11"/></svg>',
  file: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M9 13h6M9 17h6"/></svg>',
  check: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>',
  x: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>',
  clock: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  receipt: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/><path d="M14 8H8M16 12H8M13 16H8"/></svg>',
  user: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="m16 11 2 2 4-4"/></svg>',
  lock: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
  bank: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M6 12h.01M18 12h.01"/></svg>',
  box: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>'
};
$("brand-icon").innerHTML = ICONS.shield;
document.querySelectorAll("[data-icon]").forEach((el) => {
  el.innerHTML = ICONS[el.dataset.icon] || "";
});

const REASONS = {
  category_not_allowed: "category is not on the policy allowlist",
  over_budget: "price exceeds the job's budget cap",
  price_changed: "checkout price differs from the quoted price",
  approver_denied: "the console approver said no"
};
const EXP_TAG = {
  capture: ["exp-capture", "expects capture"],
  block_guardrail: ["exp-guard", "expects guardrail block"],
  block_approver: ["exp-approver", "expects approver block"]
};

let jobsById = {}, selectedJob = null, currentMode = {mode: "mock"};
let lastSessionJSON = "", lastLogJSON = "";

async function api(path, opts) {
  const r = await fetch(path, opts);
  return r.json();
}
const post = (path, body) => api(path, {
  method: "POST", headers: {"Content-Type": "application/json"},
  body: JSON.stringify(body || {})
});

/* ---------------- jobs + mode ---------------- */
async function loadJobs() {
  const d = await api("/api/jobs");
  currentMode = d.mode || currentMode;
  const badge = $("mode-badge");
  badge.className = "mode-badge" + (d.mode.mode === "live" ? " live" : "");
  badge.innerHTML = "<b>" + esc(d.mode.label) + "</b><span class='sub'>" +
    esc(d.mode.detail) + "</span>";
  $("jobs-sub").textContent = "The frozen task set v" + d.version +
    " — defined before the runner was wired, checksum-pinned. Expected " +
    "outcomes shown; the console reports what actually happens, misses included.";
  const list = $("jobs");
  list.innerHTML = "";
  d.jobs.forEach((j) => {
    jobsById[j.id] = j;
    const tag = EXP_TAG[j.expected_outcome] || ["", j.expected_outcome];
    const row = document.createElement("div");
    row.className = "job"; row.dataset.id = j.id;
    row.innerHTML =
      "<span class='jid'>" + esc(j.id) + "</span>" +
      "<span class='jmain'><span class='jtitle'>" + esc(j.title) + "</span><br>" +
      "<span class='jitem'>" + esc(j.item) + " · " + esc(j.merchant) + "</span></span>" +
      "<span class='tag " + tag[0] + "'>" + tag[1] + "</span>" +
      "<span class='jamt'>" + money(j.checkout_price) + "</span>";
    row.addEventListener("click", () => selectJob(j.id));
    list.appendChild(row);
  });
}
function selectJob(id) {
  selectedJob = id;
  document.querySelectorAll(".job").forEach((el) =>
    el.classList.toggle("selected", el.dataset.id === id));
  $("run-job-btn").disabled = false;
}

/* ---------------- session rendering ---------------- */
function step(state, icon, label, chip, desc, result) {
  return "<div class='step " + state + "'><div class='dot'>" + icon + "</div>" +
    "<div class='sbody'><div class='slabel'>" + label + (chip || "") + "</div>" +
    "<div class='sdesc'>" + desc + "</div>" +
    (result ? "<div class='sresult'>" + result + "</div>" : "") +
    "</div></div>";
}
const CHIP_CODE = "<span class='chip code'>deterministic code</span>";
const CHIP_PP = "<span class='chip paypal'>PayPal's step</span>";
const CHIP_GATE = "<span class='chip gate'>Approve-to-Pay gate</span>";

function renderSession(s) {
  const errBox = $("run-error");
  if (s.status === "error") {
    errBox.style.display = "block";
    errBox.textContent = "Run failed: " + (s.error || "unknown error");
  } else errBox.style.display = "none";
  if (!s.job) return;
  const j = s.job, e = s.entry;
  $("idle-note").style.display = "none";
  $("steps").style.display = "flex";
  $("run-title").textContent = j.id + " — " + j.title;
  $("run-meta").textContent = j.item + " · " + j.merchant + " · category " +
    j.category + " · mode: " + (s.mode ? s.mode.label : "");
  $("run-amount").style.display = "block";
  $("run-amt").textContent = money(j.checkout_price);
  $("run-cap").textContent = "quoted " + money(j.quoted_price) +
    " · budget cap " + money(j.budget_cap);

  const out = [];

  /* 1 — guardrail */
  if (e) {
    if (e.guardrail_verdict === "pass") {
      out.push(step("done", ICONS.shield, "Guardrail", CHIP_CODE,
        "Budget cap, category allowlist, price drift — checked in pure code, no model judgment.",
        "<span class='ok-text'>PASS</span> — every check green; an order may be created."));
    } else {
      out.push(step("blocked", ICONS.shield, "Guardrail", CHIP_CODE,
        "Budget cap, category allowlist, price drift — checked in pure code, no model judgment.",
        "<span class='reason'>BLOCKED — " + esc(REASONS[e.guardrail_reason] || e.guardrail_reason) +
        "</span> <span class='mono'>(" + esc(e.guardrail_reason) + ")</span>. " +
        "The job stops here: no order is created, no money can move."));
    }
  } else {
    out.push(step("active", ICONS.shield, "Guardrail", CHIP_CODE,
      "Budget cap, category allowlist, price drift — checked in pure code, no model judgment.",
      "Checking…"));
  }

  /* 2 — order */
  const orderId = (e && e.order_id) || s.order_id;
  if (orderId) {
    const captured = e && e.capture_status === "COMPLETED";
    const pill = captured
      ? "<span class='pill completed'>COMPLETED</span>"
      : "<span class='pill uncaptured'>UNCAPTURED</span>";
    out.push(step("done", ICONS.box, "PayPal order created", "",
      "Orders API v2 · intent CAPTURE · the order exists before any money moves.",
      "Order <span class='mono'>" + esc(orderId) + "</span> &nbsp;" + pill));
  } else if (e) {
    out.push(step("pending", ICONS.box, "PayPal order", "",
      "Orders API v2 · intent CAPTURE.",
      "Skipped — the guardrail blocked this job before an order could exist."));
  } else {
    out.push(step("pending", ICONS.box, "PayPal order", "",
      "Orders API v2 · intent CAPTURE.", ""));
  }

  /* 3 — payer approval (PayPal's step) */
  const payerDone = (e && e.payer_approval === "approved") ||
    s.status === "awaiting_console" || (e && e.approver_decision !== "not_reached");
  if (payerDone) {
    const fixtureNote = (s.mode && s.mode.mode === "mock")
      ? " Recorded by the Orders API fixture in SANDBOX-FIXTURE mode." : "";
    out.push(step("done", ICONS.user, "Payer approval", CHIP_PP,
      "The payer approves the payment on PayPal's own page. PayPal's step — not our gate.",
      "<span class='ok-text'>Approved.</span>" + fixtureNote));
  } else if (e) {
    out.push(step("pending", ICONS.user, "Payer approval", CHIP_PP,
      "The payer approves the payment on PayPal's own page. PayPal's step — not our gate.",
      "Not reached."));
  } else {
    out.push(step(orderId ? "active" : "pending", ICONS.user, "Payer approval", CHIP_PP,
      "The payer approves the payment on PayPal's own page. PayPal's step — not our gate.", ""));
  }

  /* 4 — console approval (our gate) */
  if (s.status === "awaiting_console") {
    out.push(step("active", ICONS.lock, "Console approval", CHIP_GATE,
      "Approve-to-Pay's human gate. Nothing is captured until the approver decides — the order above is still UNCAPTURED.",
      "<div class='uncaptured-banner'>" + ICONS.clock +
        "<span><b>Waiting for the approver.</b> Order <span class='mono'>" +
        esc(orderId || "") + "</span> is UNCAPTURED — $" + money(j.checkout_price).slice(1) +
        " held, $0 moved.</span></div>" +
        "<div class='gate-actions'>" +
        "<button class='approve' data-decide='approve'>Approve — capture " +
        money(j.checkout_price) + "</button>" +
        "<button class='deny' data-decide='deny'>Deny — capture nothing</button>" +
        "<span class='hint'>Deny is final: capture is never called.</span></div>"));
  } else if (e && e.approver_decision === "approve") {
    out.push(step("done", ICONS.lock, "Console approval", CHIP_GATE,
      "Approve-to-Pay's human gate.",
      "<span class='ok-text'>Approved</span> — the approver authorized this exact spend."));
  } else if (e && e.approver_decision === "deny") {
    out.push(step("blocked", ICONS.lock, "Console approval", CHIP_GATE,
      "Approve-to-Pay's human gate.",
      "<span class='reason'>Denied.</span> The approver said no — capture is never called." +
      (s.decision_note ? " <span class='hint'>" + esc(s.decision_note) + "</span>" : "")));
  } else if (e) {
    out.push(step("pending", ICONS.lock, "Console approval", CHIP_GATE,
      "Approve-to-Pay's human gate.", "Not reached — the run stopped earlier."));
  } else {
    out.push(step("pending", ICONS.lock, "Console approval", CHIP_GATE,
      "Approve-to-Pay's human gate.", ""));
  }

  /* 5 — capture */
  if (e && e.capture_called && e.capture_status === "COMPLETED") {
    out.push(step("done", ICONS.bank, "Capture", "",
      "The only step that moves money — reached only on guardrail pass + payer approval + console approval.",
      "<span class='pill completed'>COMPLETED</span>" +
      "<div class='receipt'><b>Receipt.</b> PayPal order <span class='mono'>" +
      esc(e.order_id) + "</span> captured — <b>" + money(e.amount) +
      "</b> · status COMPLETED. The captured order is the receipt.</div>"));
  } else if (e && e.actual_outcome === "block_approver") {
    const proof = JSON.stringify({
      ts: e.ts, job_id: e.job_id, order_id: e.order_id,
      guardrail_verdict: e.guardrail_verdict,
      approver_decision: e.approver_decision,
      capture_called: e.capture_called, amount: e.amount
    }, null, 1);
    out.push(step("blocked", ICONS.bank, "Capture", "",
      "The only step that moves money.",
      "<span class='pill never'>CAPTURE NEVER CALLED</span>" +
      "<div class='zero'><b>$0 moved.</b> The order stays uncaptured. " +
      "The decision-log entry below is the proof — verify it in the log, don't take the UI's word for it.</div>" +
      "<div class='proof'>" + esc(proof) + "</div>"));
  } else if (e && e.actual_outcome === "block_guardrail") {
    out.push(step("pending", ICONS.bank, "Capture", "",
      "The only step that moves money.",
      "Not reached — no order exists, <b>$0 moved</b>. The guardrail's log entry records <span class='mono'>capture_called: false</span>."));
  } else if (s.status === "awaiting_console") {
    out.push(step("pending", ICONS.bank, "Capture", "",
      "The only step that moves money.", "Waiting on the console approver above."));
  } else {
    out.push(step("pending", ICONS.bank, "Capture", "",
      "The only step that moves money.", ""));
  }

  $("steps").innerHTML = out.join("");
  $("steps").querySelectorAll("[data-decide]").forEach((b) =>
    b.addEventListener("click", () => decide(b.dataset.decide)));
}

async function decide(d) {
  document.querySelectorAll("[data-decide]").forEach((b) => b.disabled = true);
  await post("/api/decide", {decision: d});
  pollSession();
}

async function pollSession() {
  const s = await api("/api/session");
  const js = JSON.stringify(s);
  if (js === lastSessionJSON) return;
  lastSessionJSON = js;
  renderSession(s);
  if (s.status === "done" || s.status === "error") loadLog();
}

/* ---------------- report ---------------- */
function renderReport(r) {
  if (!r) { $("report-body").innerHTML = "<p class='sub'>No batch run recorded yet.</p>"; return; }
  const reasons = Object.entries(r.blocked_by_guardrail_by_reason || {})
    .map(([k, v]) => "<div class='kv'><span class='k mono'>" + esc(k) + "</span>" +
      "<span class='v'>" + v + "</span></div>").join("");
  const miss = (list) => list && list.length
    ? "<span class='some'>" + list.map(esc).join(", ") + "</span>"
    : "<span class='none'>none</span>";
  $("report-sub").textContent = "Task set v" + r.task_set_version + " · mode " +
    r.mode + " · outcomes matching expectations: " + r.outcome_matches + "/" + r.total_jobs;
  $("report-body").innerHTML =
    "<div class='stats'>" +
    "<div class='stat hero'><div class='n'>" + money(r.blocked_moved_usd) + " moved</div>" +
    "<div class='l'>by all " + (r.blocked_by_guardrail + r.blocked_by_approver) +
    " blocked purchases — intended spend held: " + money(r.blocked_intended_spend_usd) + "</div></div>" +
    "<div class='stat'><div class='n'>" + r.captured + "</div>" +
    "<div class='l'>captured (COMPLETED) · " + money(r.captured_total_usd) + "</div></div>" +
    "<div class='stat'><div class='n'>" + r.blocked_by_guardrail + "</div>" +
    "<div class='l'>blocked by the guardrail</div></div>" +
    "</div>" +
    reasons +
    "<div class='kv'><span class='k'>Blocked by approver</span><span class='v'>" +
    r.blocked_by_approver + "</span></div>" +
    "<div class='kv'><span class='k'>Capture calls on blocked jobs</span><span class='v'>" +
    r.capture_calls_on_blocked_jobs + "</span></div>" +
    "<div class='misses'><div class='kv'><span class='k'>False blocks (expected capture, blocked)</span>" +
    "<span class='v'>" + miss(r.false_blocks) + "</span></div>" +
    "<div class='kv'><span class='k'>Missed blocks (expected block, captured)</span>" +
    "<span class='v'>" + miss(r.missed_blocks) + "</span></div></div>";
}
async function loadReport() {
  const d = await api("/api/report");
  renderReport(d.report);
}

/* ---------------- decision log ---------------- */
function renderLog(entries) {
  const el = $("loglist");
  if (!entries.length) {
    el.innerHTML = "<p class='sub'>No entries yet — run a job.</p>"; return;
  }
  el.innerHTML = entries.map((e) => {
    const outcome = e.actual_outcome === "capture"
      ? "<span class='pill completed'>CAPTURED</span>"
      : e.actual_outcome === "block_guardrail"
        ? "<span class='pill plain'>GUARDRAIL BLOCK</span>"
        : "<span class='pill never'>APPROVER BLOCK</span>";
    const t = e.ts ? new Date(e.ts).toLocaleString() : "";
    return "<div class='lrow'><div class='ltop'><b>" + esc(e.job_id) + "</b>" +
      outcome + "<span class='mono'>" + esc(e.order_id || "no order") + "</span>" +
      "<span class='ltime'>" + esc(t) + "</span></div>" +
      "<div class='ldet'>guardrail <b>" + esc(e.guardrail_verdict) +
      (e.guardrail_reason ? " (" + esc(e.guardrail_reason) + ")" : "") +
      "</b> · payer <b>" + esc(e.payer_approval) + "</b> · approver <b>" +
      esc(e.approver_decision) + "</b> · capture_called <b>" +
      (e.capture_called ? "true" : "false") + "</b> · " + money(e.amount) +
      " · " + esc(e.mode) + "</div></div>";
  }).join("");
}
async function loadLog() {
  const d = await api("/api/log?limit=30");
  const js = JSON.stringify(d.entries);
  if (js === lastLogJSON) return;
  lastLogJSON = js;
  renderLog(d.entries);
}

/* ---------------- actions ---------------- */
$("run-job-btn").addEventListener("click", async () => {
  if (!selectedJob) return;
  const r = await post("/api/run", {job_id: selectedJob});
  if (!r.ok) { alert(r.message); return; }
  lastSessionJSON = "";
  pollSession();
});
$("run-all-btn").addEventListener("click", async () => {
  const b = $("run-all-btn");
  b.disabled = true; b.textContent = "Running 20 jobs…";
  try {
    const r = await post("/api/run-all", {});
    if (r.error) alert(r.error); else renderReport(r.report);
    loadLog();
  } finally { b.disabled = false; b.textContent = "Run all 20 jobs"; }
});

loadJobs(); loadReport(); loadLog(); pollSession();
setInterval(pollSession, 700);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
