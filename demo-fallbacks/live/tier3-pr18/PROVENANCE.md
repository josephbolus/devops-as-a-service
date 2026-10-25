# Provenance — live Tier-3 end state (PR #18)

- Source: https://github.com/josephbolus/devops-as-a-service/pull/18
- Title: "Make the CLI output machine-readable"
- State at capture: OPEN (captured Oct 25, 2026, ~8:35 AM MT)
- Created: 2026-10-25T14:32:56Z
- Head branch: `daas/make-the-cli-output-machine-readable`
- Changed files: 2 (+45 / −2) — `app/cli.py` (in the demo repo)
  and a new regression test file.
- How it was produced: a live run of the agent pipeline
  (`run_pr.py`, Oct 25, maximizer live-eval iteration) with all model
  calls served by the Meta Model API through the custom.meta-model-api
  connector (no env key). Triage, planner, coder, and reviewer each
  returned structured JSON; the reviewer approved; discovered tests
  grew 6 → 8, which the pipeline's live-coverage guard requires
  before a run can pass.
- `pr_body.md` is the PR body verbatim (`gh pr view 18 --json body`);
  `diff.patch` is `gh pr diff 18` verbatim; `pr.json` is the
  `gh pr view 18` metadata at capture.
- The timed live measurement for Tier 3 is the separate Oct 25 timed
  pipeline run recorded in `eval-scorecard/live-runs.json`
  (6 → 8 tests, 30.99s, reviewer approve).
