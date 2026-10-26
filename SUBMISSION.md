# Submission draft — DevOps as a Service (Day-8 dry run, Oct 25, 2026)

Status: **DRAFT — not submitted.** This is the Day-8 submission dry-run
artifact from the sprint plan: the full submission form text, drafted
early so Nov 4 is a paste-and-verify, not a writing day. Submitting
remains Joseph's go in the main chat. Deadline: Nov 4, 2026, 9:00 PM ET.

Honest gaps in this draft, by design:

- **Demo video: not yet recorded — no video exists yet.** The video URL
  field below is a placeholder. Recording is Joseph's Thu Oct 29 work
  (moved off Nov 2, his Philippines departure day; Nov 2 morning is
  emergency-retake only); the
  run-of-show (`DEMO_RUN_OF_SHOW.md`) and fallback package
  (`demo-fallbacks/`) are ready for it.
- Everything else in this draft is measured or test-pinned in the repo
  and linked below; model claims are labeled model, not measurement.

## Form fields (draft text)

- **Project name:** DevOps as a Service
- **Track:** Indie Dev Track — Meta Global AI Developer Hackathon 2026
- **Tagline:** One GitHub issue in → a tested pull request out — and when
  an issue is destructive, the agents stop and ask a human instead.
- **Repository:** https://github.com/josephbolus/devops-as-a-service
- **Demo video URL:** [TO BE ADDED after the Oct 29 recording — no video
  exists yet]

## Description (Impact — 30%)

Small engineering teams — two to ten developers, like the five-engineer
shop this entry is built for — lose a senior engineer's hour or more to
every small, well-defined backlog fix, so the small stuff waits for
weeks. DevOps as a Service clears that backlog: file the issue, and a
multi-agent workflow returns a reviewed, tested pull request.

Measured, not asserted: on the seeded eval set, timed live runs through
the Meta Model API passed 3/3 tiers (tests 6 → 9, 6 → 10, 6 → 8) in
94.65s total pipeline wall clock, against a 60-minute manual floor per
issue, and live runs opened PRs #16, #17, and #18. The result repeats:
the combined live record across three attempts per issue is 9/9 work
tiers (`REPEATABILITY.md`), and the pipeline also passed live on a
second codebase it had never seen (ledgerlite, tests 9 → 13;
`eval-scorecard/GENERALIZATION.md`), and on a third unseen codebase
(textkit, tests 10 → 15; `eval-scorecard/GENERALIZATION2.md`), and on a
fourth unseen codebase (gradebook, tests 12 → 18;
`eval-scorecard/GENERALIZATION3.md`) whose issue carried two defects in
two production modules — the first live fix spanning two production
files, verified by an independent probe (8/8) rather than the
pipeline's own tests alone. The worked impact model
(`IMPACT_MODEL.md`, every input labeled measured / asserted / assumed)
gives 50 min saved per passed issue and 216.7 senior hours per year at
the middle volume, at an estimated API cost of $0.0254 per passed
issue — $0.0305 per senior-hour saved (`eval-scorecard/COST_ACCOUNTING.md`;
character-count estimate, not billing data, because the API does not
expose usage on the connector path). Honest limits: n=3 seeded issues
(three attempts each) plus three generalization issues (n=1 each, on
three different unseen codebases), no real users
yet, and review time is still the model's 10-minute assumption.

- Eval scorecard: `eval-scorecard/SCORECARD.md`
- Live PRs: https://github.com/josephbolus/devops-as-a-service/pull/16,
  https://github.com/josephbolus/devops-as-a-service/pull/17,
  https://github.com/josephbolus/devops-as-a-service/pull/18

## How it uses Meta AI (Use of Meta AI Tooling — 25%)

All model calls go through one `llm` abstraction (`daas/llm.py`) to the
Meta Model API, with `response_format: json_object` and four
schema-pinned role prompts (triage, planner, coder, reviewer — exact
JSON keys in `META_AI_TOOLING.md`). A measured per-role split experiment
(Oct 25, decision rule registered before the runs) keeps the split:
CODER/REVIEWER on `muse-wonder-1.0`, TRIAGE/PLANNER on
`muse-spark-1.3` — pass counts tied 4/4 with the uniform configuration,
test growth won +10 vs +9, at 209.14s vs 94.65s wall clock. The cost is
recorded, not hidden. Record: `eval-scorecard/split-runs.json`.
Provider-transient resilience: after the live tour's Tier 2 run was
lost to a provider HTTP 503, both live clients gained transient-only
retry (HTTP 429/500/502/503/504, exponential backoff, max 3 attempts;
auth/4xx never retried; per-client `retry_stats` recorded) — recovery
pinned against simulated 503s, and Tier 2 re-validated live under the
retrying client: passed 6 → 10, reviewer approve, retries=0 (the
provider did not blip that run, so no live retry is claimed;
`eval-scorecard/RETRY.md`, `eval-scorecard/retry-runs.json`).
Model fallback (Oct 26): both live clients also fall back to a
configured alternate model only on model-availability failures
(HTTP 404 / `model_not_found`) or transient exhaustion — never on
auth/4xx — recording `fallback_stats`. Live: probes answered ok for
four Meta models (`muse-spark-1.3`, `muse-wonder-1.0`,
`muse-spark-1.2`, `muse-spark-1.1`); a controlled exercise with a
deliberately invalid primary drew a real provider 404 and the
fallback `muse-spark-1.2` answered (fallbacks 1, successes 1); and
the full seeded set passed live with every role on
`muse-spark-1.2` — Tier 1 6 → 13, Tier 2 6 → 14, Tier 3 6 → 11,
guardrail escalated, 88.59s, growth +20, est. $0.0309 total (char
estimate; spark-1.2 priced at spark-1.3 rates). One pass on the
seeded set: the kept split is NOT re-decided on it
(`eval-scorecard/MODEL_FALLBACK.md`,
`eval-scorecard/model-fallback-runs.json`). And the last
probe-only model is now pipeline-proven: the full seeded set
passed live with every role on `muse-spark-1.1` — Tier 1
6 → 10, Tier 2 6 → 9, Tier 3 6 → 9, guardrail escalated, growth
+10, 77.67s, est. $0.0245 total (char estimate; spark-1.1 priced
at spark-1.3 rates) (`eval-scorecard/SPARK11.md`,
`eval-scorecard/spark11-runs.json`). The spark-1.2 configuration
has now been replicated (iteration 30): a second live pass with
every role on `muse-spark-1.2` passed 3/3 + guardrail again —
Tier 1 6 → 11, Tier 2 6 → 10, Tier 3 6 → 11, growth +14,
114.74s, est. $0.0262 total — so its two-pass growth is +20 and
+14 (mean +17.0): the original +20 did not repeat exactly and
reads as the high end of variance, stated in
`eval-scorecard/SPARK12_REPLICATE.md` and
`eval-scorecard/spark12-replicate-runs.json`. The kept split is
still NOT re-decided on these passes.

## Demo (25%)

The demo (script + `DEMO_RUN_OF_SHOW.md`) runs the pipeline live in a
stdlib-only console: issue picker, Mock/Live toggle, and a stage
timeline (guardrail → triage → plan → code → tests → review → done).
Beats: a live Tier-1 fix opening a PR, then the trust beat — a
destructive issue ("Delete the legacy database and drop old tables")
escalates before any model call, and the human completes the
approve-and-resume decision in the console itself. Every beat has a
walkable fallback in `demo-fallbacks/`. A judge needs no operator at
all: Judge Mode (`JUDGE_MODE.md`) runs any seeded issue from one click
with narration captions tied to each pipeline event and a closing
results card — and the full tour is measured, all four stops over
HTTP: work issues 3/3 pass, the guardrail stop ends escalated
(`eval-scorecard/JUDGE_TOUR.md`). Judge Mode has also run live end
to end through the same one-click endpoint: Tier 1 pass, tests
6 → 9, 20.44s, est. $0.0108 (`eval-scorecard/JUDGE_LIVE.md`) — and
the full live tour (`eval-scorecard/JUDGE_LIVE_TOUR.md`): Tier 1
and Tier 3 passed live, the guardrail stop escalated live, and
Tier 2's card honestly reported fail after a provider HTTP 503
interrupted its reviewer call (its tests stage had passed 6 → 11).
Video status: not yet recorded.

## Technical depth & execution (20%)

- A deterministic guardrail (`daas/guardrail.py`) runs before any model
  call; models never decide safety. Pinned: 10 destructive phrasings
  escalate, 7 benign cleanups pass.
- Approve-and-resume (`APPROVE_AND_RESUME.md`): validated human
  decisions; reject / handle-manually close with zero model calls
  (counting-client pinned); re-scope is the only resumable path and
  re-runs the guardrail. Measured Oct 25: mock rescope passed 6 → 7;
  live rescope under the split passed 6 → 9 in 16.84s
  (`eval-scorecard/resume-runs.json`).
- Negative controls (`eval-scorecard/NEGATIVE_CONTROLS.md`): three
  pre-registered live issues that must NOT pass — a false bug report
  and a spec contradicting the docstring/baseline were both correctly
  not passed (reviewer request_changes; no baseline test was edited
  to fit), but a bug report about a non-existent
  `gradebook/statistics.py` FALSE-PASSED: the pipeline invented the
  module and the reviewer approved (12 → 18). That record stands.
  The fix is a deterministic plan gate (`daas/pipeline.py`): for a
  bug report, a plan naming a non-test production file absent from
  the repo escalates before the coder runs (features exempt); the
  same control re-ran live and escalated in 14.14s after 2 model
  calls (`eval-scorecard/PLAN_GATE.md`,
  `negative-controls-recheck.json`). The same three control shapes
  then ran live on a second codebase (textkit;
  `eval-scorecard/NEGATIVE_CONTROLS2.md`): 3/3 handled — false report
  and contradictory spec failed via reviewer request_changes (no
  baseline-test tampering), and the non-existent-target control
  escalated via the plan gate in 6.16s after 2 model calls, no file
  created — the gate generalizes beyond the codebase that motivated
  it. At that point the false-report shape was still stopped only
  by the reviewer; that caveat is now closed by a second
  deterministic gate (iteration 26): the regression gate in
  `daas/pipeline.py` restores the changed production files to
  baseline after the coder runs, re-runs the suite with the coder's
  tests in place, and a run may pass only if that suite FAILS on the
  baseline — a regression test that passes on unfixed code proves
  nothing. Measured live on textkit
  (`eval-scorecard/REGRESSION_GATE.md`): the genuine first_words bug
  passed 10 → 14 with the gate verified (suite fails on baseline),
  and the false-report control was blocked by the gate
  deterministically (its 13 tests pass on baseline too), in
  `eval-scorecard/regression-gate-runs.json`. The reviewer receives
  the gate result as context and cited it; the block itself is
  computed in code, not by the reviewer.
- Regression-gate generalization + a NEW measured failure (iteration
  27; `eval-scorecard/REGRESSION_GATE2.md`): on gradebook the gate
  verified the genuine multi-file fix (12 → 17, both production
  modules restored to baseline and re-checked), but the gradebook
  false-report control FALSE-PASSED by a new shape — the coder
  ignored the falsely-claimed `simple_mean` and fixed the genuine
  `weighted_mean` bug in the same file instead (12 → 16), so the
  regression gate verified a real but OFF-TARGET change. That record
  stands. The fix is a third deterministic gate, the issue-target
  gate in `daas/pipeline.py`: when the issue names existing repo
  functions, a run may pass only if the production change actually
  modifies at least one of them (function source segments compared
  baseline vs after; not applicable when the issue names no existing
  function), pinned by `tests/test_target_gate.py` (genuine Tier-1
  passes; an off-target stub client cannot pass). Live recheck of
  the exact control (`eval-scorecard/TARGET_GATE.md`): the run did
  NOT pass (12 → 14, reviewer request_changes) — this time the coder
  stayed on target with a behavior-preserving refactor, so the
  regression gate blocked it deterministically; the recheck's
  pre-registered target-gate-specific handled definition was NOT
  met and the record says so.
- Architecture, trust boundaries, and component map: `ARCHITECTURE.md`.
- Suites at drafting: scaffold 254/254, demo repo 6/6, generalization
  package 9/9, generalization2 package 10/10, generalization3 package
  12/12, all stdlib-only.

## Dry-run checklist (Day 8 exit criteria)

- [x] README polish: what it is, architecture, scorecard, how to run
- [x] Architecture diagram published (`ARCHITECTURE.md`)
- [x] Scorecard complete and public (`eval-scorecard/`, no pending rows)
- [x] License file present (`LICENSE`, MIT)
- [x] Submission form text drafted (this file)
- [x] No secrets in the repo: the API key lives only in the secure
  connection store / environment; `.gitignore` covers `.env*` and
  `*.key`; tracked files contain no key values
- [x] Branches: `main` plus the three `daas/*` branches, each backing an
  open live PR (#16/#17/#18) — not stray branches
- [ ] Demo video recorded (Thu Oct 29, Joseph) and URL pasted above
- [ ] Final submission sent (Nov 4, Joseph's go only)
