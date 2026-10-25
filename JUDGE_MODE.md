# Judge Mode — the self-guided demo console mode

Built Oct 25, 2026 (maximizer new-feature backlog item 2, targeting the
Demo criterion). A judge can run the system with **no operator**: one
click in the demo console, narration as the work happens, and a
results card at the end — no one needs to explain what they are
looking at.

## How to run it

```bash
cd hackathon-agent-scaffold
python3 demo_ui.py            # http://127.0.0.1:8765/
```

Click **▶ Run Judge Mode**. It launches the Tier 1 issue in Mock mode
(offline, deterministic — the safe default for an unattended judge;
the same endpoint accepts `{"issue_id": "guardrail", "mode": "mock"}`
for the escalation tour, or `"mode": "live"` where the connector is
configured). Programmatically: `POST /api/judge/run`, then poll
`GET /api/run/<run_id>` as usual.

## What it does

- **Narration captions tied to events, not a script.** Every pipeline
  event (`guardrail → triage → plan → code → tests → review → done`)
  is stamped when it fires with a caption generated from that event's
  own data (`demo_ui.caption_for_event`): the triage kind, the plan's
  step count, the files the coder changed, the exact test-count delta,
  the reviewer's verdict. The guardrail-escalation caption states
  plainly that no model ran. Captions travel in the run snapshot
  (`events[].caption` and the top-level `captions` list) and render in
  the console's Narration panel as stages fire.
- **Per-stage timings.** Each event carries `elapsed_ms`, recorded by
  the console's collector from the run's start — the results card
  shows when each stage actually fired, not an estimate.
- **A closing results card** (`demo_ui.results_card`, also returned as
  `results_card` in every run snapshot): overall pass / fail /
  escalated, pass/fail **per stage**, the test-count delta, total
  elapsed time, the run's per-role API cost summary (from the
  pipeline's own `cost` block — an estimate, labeled as such; mock
  and guardrail runs show $0.00), and links — this run's PR (when
  one was opened), the
  three live PRs (#16/#17/#18), the eval scorecard, and the
  generalization record. A failing tests stage or a non-approving
  reviewer is named as failing in the card; an escalated run ends as
  escalated with the later stages pending, never as a pass.

## What it does not do

- It does not change pipeline behavior: Judge Mode is presentation
  over the same `on_event` stream the operator console already used.
- Mock is the one-click default, and mock proves plumbing, not model
  performance — the card's links point at the live evidence (PRs and
  scorecard) for the model-performance claims.
- It is not the demo video. Nothing is recorded; Joseph's Nov 2
  recording remains the Demo criterion's human-owned item.

## Full tour record (Oct 25, iteration 18)

Judge Mode was initially HTTP-proven on two stops (Tier 1, guardrail).
`hackathon-agent-scaffold/run_judge_tour.py` now runs the one-click
endpoint over real HTTP for **all four** seeded issues in mock mode
and records every stop's results card in
`eval-scorecard/judge-tour.json` / `eval-scorecard/JUDGE_TOUR.md`:
Tier 1/2/3 pass (test deltas +1/+3/+2, combined +6, 7 captions each),
the guardrail stop ends escalated with its later stages pending
(1 caption). Mock is plumbing proof, not model performance — the tour
proves a judge can reach every stop unaided, nothing more.

## Pinned by tests

`tests/test_judge_tour.py` pins the tour record (summary recomputed
from the per-run rows; the doc must agree with the record).
`tests/test_judge_mode.py` (8 tests): a caption exists and is
event-derived for every stage (including blocked-guardrail and
failing-tests variants), the results card's pass/fail/delta/link
logic on synthetic snapshots (pass, tests-fail, escalated), the page
contains the Judge Mode wiring, and two full judge runs over real
HTTP — Tier 1 completes with a passing card (test delta +1, all
stages pass, captions + timings on every event) and the guardrail
issue ends escalated with the no-model caption.
