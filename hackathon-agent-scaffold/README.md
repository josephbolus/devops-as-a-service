# DevOps as a Service — agent-loop scaffold (pre-built Oct 22, 2026)

Pulls the sprint plan's Days 1–2 work (Oct 27–28: triage → planner →
coder → reviewer → PR) forward into a tested skeleton, so the sprint
starts from working plumbing instead of a blank repo. Repo-agnostic,
like the issue pack: it drops into whichever repo the user picks, and
nothing here has been pushed to GitHub.

## What's proven (verified Oct 22 evening, local run)

- `python3 -m unittest discover -s tests` — 2/2 pass.
- Tier-1 end-to-end with the mock provider, against a copy of
  `../hackathon-demo-repo`: issue in → guardrail pass → triage → plan →
  coder edits applied → 7 tests green (6 baseline + new regression) →
  reviewer approve → `pr_body.md` written. `paginate(range(20), 2, 10)`
  returns 10 after the run.
- Guardrail issue ("Delete the legacy database…"): escalates before
  any agent runs, writes `escalation.md`, repo files byte-identical.
- Guardrail coverage hardened Oct 24: a probe found 5 of 5 reworded
  destructive requests ("Erase the production database", "Permanently
  delete all customer data", …) evaded the original patterns. Patterns
  now cover broad verb/object sets in both word orders, and
  `tests/test_guardrail.py` pins 10 destructive phrasings that must
  escalate and 7 benign cleanups that must pass. Full scaffold suite:
  10/10 (was 8/8 before the new tests).
- Eval set completed Oct 25 (maximizer iteration 2): `issues/tier2.json`
  (HTTP retry with backoff: 3 retries, 100ms base, 5xx/network only,
  never 4xx) and `issues/tier3.json` (CLI `--json` flag, schema from
  the REPORT dict) now exist alongside Tier 1 and the guardrail issue —
  previously Tier 2/3 lived only as code comments. `MockClient` is now
  issue-aware, with canned Tier-2/Tier-3 fixes, so all three tiers run
  end-to-end in mock mode against a demo-repo copy: Tier 2 passes with
  9 tests in the copy, Tier 3 with 8. `tests/test_eval_set.py` pins
  all four seed files (parse, exact titles, work issues pass the
  guardrail, guardrail issue blocks). Full scaffold suite: 14/14.

- Eval scorecard runner added Oct 25 (maximizer iteration 4):
  `run_scorecard.py` publishes the Days 3–4 scorecard early in
  `../eval-scorecard/` — it runs all four seeded issues in mock mode
  against fresh demo-repo copies and records the sprint plan's pass
  criteria (work tiers 3/3, guardrail escalated, zero unexpected
  files), then folds in the live Tier-1 row parsed from the captured
  PR #16 artifacts. Mock and live sections are labeled separately:
  mock is plumbing proof, live is the only model-performance
  evidence, and live Tier 2/3 + guardrail rows are listed as pending
  their scheduled sprint days. `tests/test_scorecard.py` pins all of
  it. Full scaffold suite: 25/25.

- Human-approval handoff added Oct 25 (maximizer iteration 5):
  `daas/approval.py` turns a guardrail escalation into a structured
  approval request — a walkable `escalation.md` plus a machine-readable
  `approval_request.json` recording what the pipeline provably did NOT
  do (0 model calls, no agents, no files changed, no PR), the three
  decisions a human can make (reject / re-scope / handle manually),
  and a blank decision record. This is a loop-sized slice of the
  Days 5–6 human-approval gate: the request format is built and
  pinned by `tests/test_approval.py`; the approve-and-resume flow
  remains sprint work. Full scaffold suite: 30/30.
- Architecture diagram added Oct 25 (maximizer iteration 6):
  repo-root `../ARCHITECTURE.md` is the Day-8 artifact published
  early — a Mermaid system diagram (guardrail before any model call,
  work path and escalation path, eval loop), a component map naming
  the real files above, the four trust boundaries, and an honest
  not-built-yet section (approve-and-resume is Days 5–6; live Tier
  2/3 are Days 3–4; the per-role split is a Day-1 decision).
  `tests/test_architecture.py` pins the diagram against the code:
  every named file must exist. Full scaffold suite: 36/36.
- Demo fallback package added Oct 25 (maximizer iteration 3):
  `../demo-fallbacks/` holds a walkable end state for every demo
  beat — mock Tier 1/2/3 PR bodies, results and diffs plus the
  guardrail escalation (regenerate with
  `python3 generate_demo_fallbacks.py`), and the captured LIVE
  Tier-1 end state (PR #16, a real Meta API run: tests 6 → 8,
  reviewer approved) under `live/tier1-pr16/` with a provenance
  note. Mock and live artifacts are labeled as such throughout, and
  `tests/test_demo_fallbacks.py` pins the package's completeness.
- Demo run-of-show added Oct 25 (maximizer iteration 7):
  repo-root `../DEMO_RUN_OF_SHOW.md` is the Nov 2 operator sheet —
  timed beats (2:30–3:00) mapped to the demo console's stage
  timeline (guardrail → triage → plan → code → tests → review →
  done), a Mock-mode pre-flight, fallback decision thresholds
  pointing at `../demo-fallbacks/`, and the two-take rehearsal log.
  It also scores the demo console itself (commit 698a628, unscored
  in iteration 6). `tests/test_demo_run_of_show.py` pins the stage
  order, timings, and every fallback path's existence. Full
  scaffold suite: 49/49. Still not recorded — no video exists yet.

## Demo console (added Oct 25)

`demo_ui.py` — a local web UI over the pipeline, stdlib only
(`http.server` + threading; no dependencies, no CDN assets):

```bash
python3 demo_ui.py [--port 8765]   # then open http://127.0.0.1:8765/
```

What it shows, live as it happens: an issue picker (Tier 1/2/3 +
guardrail), a Mock/Live mode toggle, and a stage timeline that fills
in via `pipeline.run`'s new `on_event` hook — guardrail verdict,
triage (kind + summary + acceptance), plan (steps), code (files
changed + full diff), tests (discovered count before → after,
pass/fail), review (verdict + notes), and the final result (PR body,
or the real PR link). A "Try to break it" panel posts arbitrary text
to `daas/guardrail.py`; escalations render the human-approval handoff
from `daas/approval.py` (what the pipeline provably did NOT do, plus
the three human options).

Safety shape: mock and live-without-PR runs execute against a fresh
throwaway copy of `../hackathon-demo-repo` (git-initialized so diffs
render) — the pristine demo repo is never mutated. Live mode resolves
the Meta Model API through `daas.llm.default_client()` (the connector
path); no key is read, accepted, or logged by the UI. Only Live +
"Open real PR" touches the real repo, by driving the refactored
`run_pr.run()` in-process and surfacing the opened PR's URL.
`tests/test_demo_ui.py` pins the event order and the HTTP endpoints
(mock mode, ephemeral port). Full scaffold suite: 42/42.

## Design choices worth knowing

- **Guardrail is deterministic code, not a prompt** (`daas/guardrail.py`).
  It runs before the LLM; a model cannot talk its way past it. The
  Oct 31–Nov 1 guardrail milestone is now mostly wiring + demo, not
  new design.
- **One LLM abstraction** (`daas/llm.py`), agents request JSON only.
  Real provider = Meta Model API; `MockClient` exists only for offline
  tests and is labeled as such — it is not the demo intelligence.
- **PR step stops at a written PR body.** Opening the PR is one
  `gh pr create --body-file pr_body.md` once the repo exists (Day 0).

## New fact on Meta Model API access (checked Oct 22, third-party docs)

The sprint plan assumed access is secured on Day 0 after approval.
Public dev docs say the API is in **public preview and self-serve**:

- OpenAI-compatible at `https://api.meta.ai/v1`; model `muse-spark-1.3`
  (1M-token context, tool calling, structured output).
- Key is created in the Meta Model API dashboard; env var cited as
  `MODEL_API_KEY` (promptfoo docs) or `META_API_KEY` (LiteLLM docs) —
  `daas/llm.py` accepts both.
- Dashboard setup requires a payment method + legal name/address for
  billing (Lakeview Lister how-to, a third-party guide — weakest source
  of the three; treat the billing detail as likely, not verified
  against Meta's own pages).

Sources: promptfoo.dev/docs/providers/meta · docs.litellm.ai/docs/providers/meta ·
lakeviewlister.com/how-tos/meta-api-key

**Implication / open choice:** account + key could be created this
weekend, before Monday's approval, leaving Day 0 as approval + rules +
repo only. Tradeoff: the hackathon teaser mentioned $150 in Meta API
credits per participant — if credits arrive via the hackathon on
approval, a self-funded key may be unnecessary spend. Creating the
account is the user's call (it needs his payment card); nothing here
signs up for anything.

## What remains for the real build (unchanged sprint scope)

1. Real prompts per agent (mock responses are canned per issue for
   Tier 1/2/3; the real provider still needs real prompts).
2. GitHub intake: read a live issue via `gh issue view --json`, branch,
   commit, `gh pr create` (Day 0–1, once the repo choice lands).
3. ~~Eval scorecard runner (Oct 29–30) can reuse `pipeline.run` per issue~~ — done early Oct 25 (`run_scorecard.py`, see above); the Oct 29–30 work is now the live Tier 2/3 runs plus regenerating the scorecard with those rows.

## Separations (unchanged)
- No RAG prototype code. Option A only.
- Local prep only — no repo created, nothing pushed, no signup made.
