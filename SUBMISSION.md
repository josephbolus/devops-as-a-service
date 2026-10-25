# Submission draft — DevOps as a Service (Day-8 dry run, Oct 25, 2026)

Status: **DRAFT — not submitted.** This is the Day-8 submission dry-run
artifact from the sprint plan: the full submission form text, drafted
early so Nov 4 is a paste-and-verify, not a writing day. Submitting
remains Joseph's go in the main chat. Deadline: Nov 4, 2026, 9:00 PM ET.

Honest gaps in this draft, by design:

- **Demo video: not yet recorded — no video exists yet.** The video URL
  field below is a placeholder. Recording is Joseph's Nov 2 work; the
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
- **Demo video URL:** [TO BE ADDED after the Nov 2 recording — no video
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
issue, and live runs opened PRs #16, #17, and #18. The worked impact
model (`IMPACT_MODEL.md`, every input labeled measured / asserted /
assumed) gives 50 min saved per passed issue and 216.7 senior hours per
year at the middle volume. Honest limits: n=3 seeded issues, one run
each, no real users yet, and review time is still the model's 10-minute
assumption.

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

## Demo (25%)

The demo (script + `DEMO_RUN_OF_SHOW.md`) runs the pipeline live in a
stdlib-only console: issue picker, Mock/Live toggle, and a stage
timeline (guardrail → triage → plan → code → tests → review → done).
Beats: a live Tier-1 fix opening a PR, then the trust beat — a
destructive issue ("Delete the legacy database and drop old tables")
escalates before any model call, and the human completes the
approve-and-resume decision in the console itself. Every beat has a
walkable fallback in `demo-fallbacks/`. Video status: not yet recorded.

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
- Architecture, trust boundaries, and component map: `ARCHITECTURE.md`.
- Suites at drafting: scaffold 107/107, demo repo 6/6, all stdlib-only.

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
- [ ] Demo video recorded (Nov 2, Joseph) and URL pasted above
- [ ] Final submission sent (Nov 4, Joseph's go only)
