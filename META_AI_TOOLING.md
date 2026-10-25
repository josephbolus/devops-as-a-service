# Meta AI tooling — DevOps as a Service

How this entry uses the Meta Model API, written from the code as it
exists on Oct 25, 2026. Every mechanism named below is a real file in
this repo, and `hackathon-agent-scaffold/tests/test_meta_tooling.py`
pins the claims against the code — including the claims about what is
NOT decided or proven yet.

## The models and the endpoint

- Models: `muse-spark-1.3` (the default for every agent role) and,
  since the Oct 25 split experiment below, `muse-wonder-1.0` for the
  CODER and REVIEWER roles in the entry's live configuration.
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

## What is NOT claimed

- `muse-wonder-1.0` is proven live only in the CODER and REVIEWER
  roles, on the seeded set, one run per tier. The split's +1-test
  margin does not prove it better on unseeded issues or a real
  backlog, and no such claim is made.
- No other models are proven live: not `muse-spark-1.2`/`1.1`, not
  the contributor variants, and Wonder is not claimed in the TRIAGE
  or PLANNER roles (never run there).
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
