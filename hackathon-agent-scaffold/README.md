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

1. Real prompts per agent (mock responses are canned for Tier-1 only).
2. GitHub intake: read a live issue via `gh issue view --json`, branch,
   commit, `gh pr create` (Day 0–1, once the repo choice lands).
3. Tier-2/Tier-3 mock responses or go straight to the real provider.
4. Eval scorecard runner (Oct 29–30) can reuse `pipeline.run` per issue.

## Separations (unchanged)
- No Meridian Runtime code. No RAG prototype code. Option A only.
- Local prep only — no repo created, nothing pushed, no signup made.
