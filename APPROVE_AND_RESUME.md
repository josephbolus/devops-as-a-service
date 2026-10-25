# Approve-and-resume — the human gate, completed

Backlog item 3 (the former Days 5–6 milestone), completed Oct 25, 2026
ahead of the sprint calendar. Record: `eval-scorecard/resume-runs.json`,
pinned by `hackathon-agent-scaffold/tests/test_resume.py`.

## The flow

1. An issue is blocked by the deterministic guardrail before any model
   call. The pipeline writes a human approval request
   (`escalation.md` + `approval_request.json`): what it provably did
   NOT do (0 model calls, no agents, no files, no PR), and the human's
   three options.
2. A human records a decision with `daas/approval.py record_decision`
   (validated: known decision, named decider, timestamp; the input
   request is not mutated, so the original escalation stays auditable).
3. `daas/pipeline.py resume` acts on the decision:
   - **reject** → closed (`closed_rejected`). Nothing runs.
   - **handle_manually** → closed (`closed_manual`). The agents never
     run the destructive work; a human does it, if at all, outside
     the pipeline.
   - **rescope** → the only resumable decision, and only with an
     explicit, narrower replacement issue attached. The replacement
     re-enters `pipeline.run`, so the guardrail re-checks it before
     any model call — a rescoped issue that is still destructive
     escalates again with a fresh approval request.
4. The outcome is written to `resume_result.json` in the run's output
   directory.

Interfaces: `run_resume.py` (CLI: request + decision + optional
rescoped-issue file, mock or live), `pipeline.resume` (programmatic,
emits a `resume` stage event then the normal stage timeline), and the
demo console (`POST /api/approval/decide` + decision buttons in the
"Try to break it" panel record the decision on the handoff and report
whether it is resumable).

## Measured flows (Oct 25)

| Mode | Escalation | Decision | Resumed run | Time |
|---|---|---|---|---|
| Mock | guardrail issue escalated, 0 model calls | rescope → Tier 1 issue | passed, tests 6 → 7 | 0.16s resume |
| Live (connector, split config) | guardrail issue escalated, 0 model calls | rescope → Tier 1 issue | passed, tests 6 → 9 | 38.02s resume |

Live role models for the resumed run: TRIAGE/PLANNER
`muse-spark-1.3`, CODER/REVIEWER `muse-wonder-1.0` (the kept split
from the iteration-11 experiment).

## What is pinned by tests

`tests/test_resume.py`: decision validation (unknown decision, missing
decider/timestamp, rescope without a replacement issue all raise);
reject and handle-manually close with **zero model calls** (a counting
client proves it) and a byte-identical repo; rescope resumes in mock
mode and passes; a still-destructive rescope re-escalates with zero
model calls; resume with no decision recorded raises; the console's
decision helper records correctly. The committed
`eval-scorecard/resume-runs.json` record itself is also pinned
(mock + live flows both escalated, both rescoped, both passed).
