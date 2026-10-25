# Meta AI tooling — DevOps as a Service

How this entry uses the Meta Model API, written from the code as it
exists on Oct 25, 2026. Every mechanism named below is a real file in
this repo, and `hackathon-agent-scaffold/tests/test_meta_tooling.py`
pins the claims against the code — including the claims about what is
NOT decided or proven yet.

## The model and the endpoint

- Model: `muse-spark-1.3` (the default for every agent role).
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

## Per-role models: mechanism proven, split NOT decided

The llm layer supports a different model per role via
`DAAS_MODEL_<ROLE>` env vars (`DAAS_MODEL_TRIAGE`,
`DAAS_MODEL_PLANNER`, `DAAS_MODEL_CODER`, `DAAS_MODEL_REVIEWER`).
`resolve_model()` picks the role's override, else the default
`muse-spark-1.3`, and BOTH live clients resolve the model before the
call — the connector helper only ever sees the final model name.
`tests/test_meta_tooling.py` pins that routing for both transports
(mocked transport, no API call).

The split itself is a Day-1 (Oct 27) decision: which roles, if any,
move off the default depends on dashboard model availability, and it
is not decided in this document. Until then every role runs
`muse-spark-1.3`.

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

## What is NOT claimed

- No model other than `muse-spark-1.3` is proven live; the per-role
  split is a mechanism, not a result.
- No tool calling, no responses endpoint (`/v1/responses`), no
  fine-tuning, and no image or audio models are used or claimed.
- Live Tier 2/3 runs are Days 3–4 sprint work; the only live
  model-performance evidence so far is the Tier-1 run (PR #16).
- `MockClient` runs prove plumbing only — never model performance.
