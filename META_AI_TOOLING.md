# Meta AI tooling — DevOps as a Service

How this entry uses the Meta Model API, written from the code as it
exists on Oct 25, 2026. Every mechanism named below is a real file in
this repo, and `hackathon-agent-scaffold/tests/test_meta_tooling.py`
pins the claims against the code — including the claims about what is
NOT decided or proven yet.

## The models and the endpoint

- Models: `muse-spark-1.3` (the code default for every agent role)
  and, since the Oct 25 split experiment below, `muse-wonder-1.0`
  for the CODER and REVIEWER roles. CONTEST CONFIGURATION (Joseph's
  Oct 26 directive, section below): ALL four roles run on the Meta
  frontier model `muse-wonder-1.0` — the strongest model verified
  through the connector (probed live Oct 26; `muse-wonder-1.1`
  returned HTTP 404 `model_not_found`). Spark-tier models remain
  configured ONLY as availability fallbacks. Since
  Oct 26 (iteration 28, Model fallback below), `muse-spark-1.2` is
  also proven live in all four roles (fallback configuration), and
  since iteration 29 `muse-spark-1.1` is proven live in all four
  roles as well.
- Endpoint: Meta Model API chat completions at `https://api.meta.ai/v1`
  (OpenAI-compatible).
- Every live call asks for structured output:
  `response_format: {"type": "json_object"}` — set in
  `daas/llm.py` for the direct client, and in the connector helper for
  the connector client. Agents reply with JSON only; the pipeline
  consumes parsed JSON, never free prose.

## One abstraction, three clients (`daas/llm.py`)

All model calls go through `LLMClient.complete_json(system, user)` in
`hackathon-agent-scaffold/daas/llm.py`. No agent talks to a provider
directly, so the transport and the model can change without touching
agent logic.

| Client | When it is used | How the key is handled |
|---|---|---|
| `ConnectorClient` | Live runs when no env key is set (the normal path) | No key in this process at all: each call shells out to the custom.meta-model-api connector helper, and the key stays in the secure connection store |
| `MetaModelClient` | Live runs when `MODEL_API_KEY` / `META_API_KEY` is set | Key read from the environment only; never written to the repo |
| `MockClient` | Offline tests and rehearsals only | No API call. Canned, deterministic, and labeled MOCK wherever its output appears — it is NOT Meta AI tooling evidence |

`default_client()` in `daas/llm.py` makes that selection: mock if
asked, direct if an env key is present, connector otherwise.

## Four roles, four schema-pinned prompts (`daas/prompts.py`)

Each system prompt starts with its role word — that first word is also
the routing convention the llm layer uses to pick a per-role model —
and pins the exact JSON schema the pipeline consumes:

| Role | Exact JSON keys | Context the pipeline supplies | What the pipeline consumes |
|---|---|---|---|
| TRIAGE | `kind`, `summary`, `acceptance` | the issue (title + body) | restated problem + acceptance criteria; the summary heads the PR body |
| PLANNER | `steps`, `expected_files` | issue + triage + the repository file tree | the plan steps, and the expected file set the unexpected-files check enforces |
| CODER | `edits` (`file`, `old`, `new`) | issue + plan + current contents of the planned files | edits applied by exact match: every `old` must quote the supplied contents verbatim, or the applier rejects it |
| REVIEWER | `verdict`, `notes` | changed files + test outcome + the actual diff | approve / request_changes; one input to the pass gate, never the gate itself |

Two coder rules are pinned in the prompt because the pipeline depends
on them: edits must quote `old` text byte-for-byte, and a regression
test must be a `unittest.TestCase` class — the suite runs
`python -m unittest discover`, which does not collect bare
pytest-style functions (the failure PR #15 taught, and the
live-coverage guard now enforces).

## Per-role split: experiment run, decision recorded

The llm layer supports a different model per role via
`DAAS_MODEL_<ROLE>` env vars (`DAAS_MODEL_TRIAGE`,
`DAAS_MODEL_PLANNER`, `DAAS_MODEL_CODER`, `DAAS_MODEL_REVIEWER`).
`resolve_model()` picks the role's override, else the default
`muse-spark-1.3`, and BOTH live clients resolve the model before the
call — the connector helper only ever sees the final model name.
`tests/test_meta_tooling.py` pins that routing for both transports
(mocked transport, no API call).

The split was the former Day-1 (Oct 27) decision; it was run early
on Oct 25, 2026 as a measured experiment, not a preference. Split
under test: CODER and REVIEWER on `muse-wonder-1.0` (Meta's most
capable model on the Model API — availability probed live through
the connector with a tiny JSON completion before the runs), TRIAGE
and PLANNER on the `muse-spark-1.3` default. Method identical to
the uniform live eval in `eval-scorecard/live-runs.json`:
`pipeline.run` per seeded issue against a fresh git-initialized
copy of the demo repo, through the connector, timed. The full
record is `eval-scorecard/split-runs.json`, produced by
`hackathon-agent-scaffold/run_split_eval.py`;
`tests/test_split_eval.py` pins the record and the decision rule.

Decision rule, registered in the runner BEFORE any split run:
(1) pass count (work tiers + guardrail), then (2) total
discovered-test growth across the work tiers, then (3) total wall
clock. The split is kept only if it wins on (1), or ties (1) and
wins on (2), or ties (1)–(2) and wins on (3); a full tie keeps
uniform, which is also the cheaper configuration per token.

| Configuration | Tier 1 | Tier 2 | Tier 3 | Guardrail | Total wall | Test growth |
|---|---|---|---|---|---|---|
| Uniform `muse-spark-1.3` | pass 6 → 9, 16.64s | pass 6 → 10, 47.02s | pass 6 → 8, 30.99s | escalated, 0 calls | 94.65s | +9 |
| Split (Wonder coder/reviewer) | pass 6 → 9, 49.40s | pass 6 → 10, 125.95s | pass 6 → 9, 33.79s | escalated, 0 calls | 209.14s | +10 |

**Decision: keep the split.** Pass counts tied at 4/4 (3/3 work
tiers + guardrail), so the rule decided on test growth: +10 vs +9
(the Wonder coder's Tier-3 run added 3 regression tests to the
uniform run's 2). The entry's live configuration is therefore
`DAAS_MODEL_CODER=muse-wonder-1.0` and
`DAAS_MODEL_REVIEWER=muse-wonder-1.0`, with TRIAGE and PLANNER on
the default — set as env vars for live runs, which
`default_client()` resolves before every call; the code default
stays `muse-spark-1.3`.

The cost is recorded, not hidden: the split took 209.14s against
the uniform run's 94.65s (about 2.2× the wall clock) and Wonder is
the premium-priced tier. The winning margin is one regression test
on n=3 seeded issues, one run each — a real but thin margin, kept
because the rule was registered before the runs, not because the
split is proven generally better.

## Contest configuration: all-frontier (Oct 26 directive)

Per Joseph's Oct 26, 2026 directive ("use meta frontier models for
the contests"), the contest configuration supersedes the split
decision above FOR CONTEST RUNS: `DAAS_MODEL_TRIAGE`,
`DAAS_MODEL_PLANNER`, `DAAS_MODEL_CODER` and `DAAS_MODEL_REVIEWER`
are ALL set to `muse-wonder-1.0`. The split experiment and its
decision rule stand above as the historical record of how the split
was chosen; they no longer describe the contest configuration.
Spark-tier models (`muse-spark-1.3`) remain configured ONLY as
availability fallbacks (`DAAS_FALLBACK_MODEL`), used solely on
model-availability failure or transient exhaustion — never as
primary role models. The all-frontier configuration is measured
live in `eval-scorecard/FRONTIER.md` + `frontier-runs.json`
(`hackathon-agent-scaffold/run_frontier_eval.py`, maximizer
iteration 31).

## Per-run cost accounting (and what the API does not expose)

Every pipeline run now carries a per-role cost summary
(`daas/cost.py`, wired into `daas/pipeline.py`): each result has a
`cost` block, each run writes `cost.json`, and the demo console's
results card surfaces it. One finding is recorded plainly: **token
usage is not exposed on the connector path** — the helper returns
only the parsed reply content, so no `usage` field ever reaches the
pipeline (the direct client likewise reads only the reply). Costs
are therefore character-count token **estimates** (~4 chars/token)
priced at the published rates (spark $1.25/$4.25, wonder $4/$20 per
1M in/out), labeled estimates in every artifact. Measured live
(split config, Oct 25): est. **$0.0254 per passed issue**, $0.0762
for the full seeded set, guardrail $0.00 — full record in
`eval-scorecard/COST_ACCOUNTING.md` and
`eval-scorecard/cost-runs.json`, pinned by
`tests/test_cost_accounting.py`. If a transport ever surfaces real
`usage`, the accounting prefers it; none does today.

## Verified live evidence

- Oct 23, 2026: smoke test — `muse-spark-1.3` answered through the
  Meta Model API with valid JSON, verifying `response_format:
  json_object` works as-is.
- Oct 25, 2026: a full live pipeline run through the
  custom.meta-model-api connector (no env key) served all four agent
  roles with structured JSON and opened PR #16 — reviewer approved,
  discovered tests 6 → 8, no unexpected files. The captured end state
  is in `demo-fallbacks/live/tier1-pr16/` with provenance, and the row
  is in `eval-scorecard/SCORECARD.md`.
- Oct 25, 2026: the timed live eval (all three tiers + guardrail,
  94.65s, PRs #16/#17/#18) in `eval-scorecard/live-runs.json`, and
  the per-role split experiment in `eval-scorecard/split-runs.json`:
  three more timed live passes with CODER/REVIEWER recorded per call
  as `muse-wonder-1.0` and TRIAGE/PLANNER as `muse-spark-1.3`,
  plus the guardrail escalation at 0 model calls.

## Provider-transient retry (Oct 25, iteration 22)

Measured motivation: the Judge Mode live tour's Tier 2 run was lost
when its REVIEWER call failed with a provider HTTP 503
(`service_overloaded`, "The backend is temporarily overloaded") and
the client raised immediately — its tests stage had already passed
6 → 11 (`eval-scorecard/JUDGE_LIVE_TOUR.md`). Both live clients in
`daas/llm.py` now retry transient failures only — HTTP
429/500/502/503/504 and overload / rate-limit / timeout markers —
with exponential backoff (1s, 2s; `max_attempts=3` total), via
`is_transient_error()`. Auth failures (`invalid_api_key`, 401/403)
and other 4xx errors are never retried. Each client records
`retry_stats` ({calls, retries, transient_failures}) so a run
reports whether a retry actually fired — no silent recovery.
Pinned by `tests/test_retry.py` (mocked transports, no live call:
connector and direct clients each recover after two 503s, fail
immediately on auth/400, and exhaust honestly after 3 attempts).
Live validation under the retrying client is recorded in
`eval-scorecard/RETRY.md` + `retry-runs.json`. Honest limit: the
retry logic is proven against simulated 503s; whether a retry
fired in the live validation run is whatever `retry_stats` in that
record says — if it says zero, no live retry is claimed.

## Model fallback (Oct 26, iteration 28)

Both live clients accept a fallback model — per role via
`DAAS_FALLBACK_<ROLE>`, or one global fallback via
`DAAS_FALLBACK_MODEL` — and use it only when the primary call fails
for a model-availability reason (HTTP 404, `model_not_found` /
unknown-model markers, via `is_model_error()`) or after transient
retries are exhausted. Auth failures and other 4xx errors never fall
back. Each client records `fallback_stats`
({fallbacks, fallback_successes}) so a fallback is reported, never
silent. Pinned by `tests/test_model_fallback.py` (mocked transports:
model-not-found and transient exhaustion fall back on both clients;
auth and 400 never do).

Live record (`eval-scorecard/MODEL_FALLBACK.md` +
`model-fallback-runs.json`, maximizer iteration 28): tiny-completion
probes through the connector answered ok for four Meta models —
`muse-spark-1.3`, `muse-wonder-1.0`, `muse-spark-1.2`, and
`muse-spark-1.1`. A controlled live fallback exercise (primary
model deliberately invalid) drew a real provider HTTP 404
`model_not_found` and the fallback (`muse-spark-1.2`) answered —
fallback_stats {fallbacks: 1, fallback_successes: 1}. The full
seeded set then ran live with every role on `muse-spark-1.2` and
passed 3/3 + guardrail (Tier 1 6 → 13, Tier 2 6 → 14, Tier 3
6 → 11, growth +20, 88.59s, est. $0.0309 total at spark-1.3 rates —
spark-1.2 has no published price in `daas/cost.py`). One pass on the
seeded set: the kept live configuration remains the measured split
above; the fallback is resilience, not a re-decision.

Spark-1.1 live record (`eval-scorecard/SPARK11.md` +
`spark11-runs.json`, maximizer iteration 29): the full seeded set
ran live with every role on `muse-spark-1.1` and passed 3/3 +
guardrail (Tier 1 6 → 10, Tier 2 6 → 9, Tier 3 6 → 9, growth +10,
77.67s, est. $0.0245 total at spark-1.3 rates — spark-1.1 has no
published price in `daas/cost.py`). Every probed spark model has
now served all four production roles live; the kept split is still
not re-decided on these single passes.

Spark-1.2 replicate record (`eval-scorecard/SPARK12_REPLICATE.md` +
`spark12-replicate-runs.json`, maximizer iteration 30): the
identical spark-1.2 all-roles configuration from iteration 28 ran
live a second time and passed 3/3 + guardrail again (Tier 1
6 → 11, Tier 2 6 → 10, Tier 3 6 → 11, growth +14, 114.74s, est.
$0.0262 total at spark-1.3 rates). Two-pass spark-1.2 growth is
therefore +20 and +14 (mean +17.0, range +14 to +20): the original
+20 did not repeat exactly — it reads as the high end of variance,
with spark-1.2 growth still above the +9/+10 band of the other
configurations on both passes. Neither pass re-decides the kept
split.

Spark-1.1 replicate record (`eval-scorecard/SPARK11_REPLICATE.md` +
`spark11-replicate-runs.json`, maximizer iteration 43): the
identical spark-1.1 all-roles configuration from iteration 29 ran
live a second time and passed 3/3 + guardrail again — at the
current 24-test demo baseline (Tier 1 24 → 29, Tier 2 24 → 29,
Tier 3 24 → 27, growth +13, 83.98s, est. $0.0260 total at
spark-1.3 rates). Two-pass spark-1.1 growth is therefore +10
(iteration 29, at the 6-test baseline) and +13 (mean +11.5);
absolute counts are not compared across the baseline change.
Every probed Meta model now has at least two live pipeline
passes. Neither pass re-decides the contest configuration
(all-frontier since iteration 31).

Frontier live record (`eval-scorecard/FRONTIER.md` +
`frontier-runs.json`, maximizer iteration 31): per Joseph's Oct 26
directive, the full seeded set ran live with EVERY role on
`muse-wonder-1.0` (contest configuration; `muse-spark-1.3`
configured only as availability fallback, fallbacks 0) and passed
3/3 + guardrail (Tier 1 6 → 8, Tier 2 6 → 12, Tier 3 6 → 8,
growth +10, 142.52s, est. $0.1124 total at wonder prices —
$0.0375 per passed issue, the highest per-issue cost of any
configuration measured, stated not hidden). Wonder has now served
all four production roles live. Probes this iteration:
`muse-wonder-1.0` answered ok; `muse-wonder-1.1` returned HTTP
404 `model_not_found` — no stronger frontier model is available
through the connector today.

Frontier replicate record (`eval-scorecard/FRONTIER_REPLICATE.md` +
`frontier-replicate-runs.json`, maximizer iteration 32): the
identical all-frontier configuration ran live a second time and
passed 3/3 + guardrail again (Tier 1 6 → 8, Tier 2 6 → 11, Tier 3
6 → 8, growth +9, 171.57s, est. $0.1112 total — $0.0371 per passed
issue; fallbacks 0, retries 0, `muse-wonder-1.0` recorded on every
role's calls). Two-pass all-frontier growth is therefore +10 and
+9 (mean +9.5, range +9 to +10), two-pass mean est. cost per
passed issue $0.0373 — still the highest per-issue cost of any
configuration measured. The contest configuration is no longer a
single-pass record.

Frontier generalization record (`eval-scorecard/FRONTIER_GENERALIZATION.md` +
`frontier-generalization-runs.json`, maximizer iteration 33): the
all-frontier contest configuration ran live on the unseen gradebook
codebase (generalization3/, 12-test baseline, two defects in two
production modules — every earlier generalization pass used the
split, and every earlier frontier pass used only the seeded set)
and passed: tests 12 → 18 (growth +6, matching the split's pass on
the same target), 32.87s, reviewer approve, no unexpected files,
the independent 8-check probe passed 8/8, est. $0.0340 (char
estimate at wonder prices; the split's pass on this target was
est. $0.0248 in 42.41s). Per-role cost records show
`muse-wonder-1.0` on every call; fallbacks 0, retries 0. The
contest configuration's record is no longer seeded-set-only.

## What is NOT claimed

- `muse-wonder-1.0` is proven live in all four roles on the
  seeded set (split runs for CODER/REVIEWER; the iteration-31/32
  all-frontier passes for every role, two passes, both 3/3 +
  guardrail) and, under the all-frontier configuration, on one
  unseen codebase (iteration 33: gradebook, 12 → 18, probe 8/8 —
  one run on a synthetic target, not a new-codebase or real-team
  claim). The split's +1-test
  margin and the frontier pass's tied +10 growth do not prove it
  better on unseeded issues or a real backlog, and no such claim
  is made.
- The contributor variants are not proven. Spark
  1.2 is proven on two passes of the seeded set and spark 1.1 on
  one pass only — no unseeded-issue claim is made for either, and
  spark 1.1 has no repeatability claim.
- No tool calling, no responses endpoint (`/v1/responses`), no
  fine-tuning, and no image or audio models are used or claimed.
- No provider-reported token usage is claimed: the connector path
  does not expose `usage`, so all token and dollar figures in the
  cost record are labeled character-count estimates.
- Live Tier 2/3 runs were completed Oct 25 (ahead of their Days 3–4
  slot): live model-performance evidence is now timed passes on all
  three tiers plus PRs #16 (Tier 1), #17 (Tier 2), and #18 (Tier 3),
  under both the uniform and the split configurations.
- `MockClient` runs prove plumbing only — never model performance.
