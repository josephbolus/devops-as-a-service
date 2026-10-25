# Provenance — live Tier-2 end state (PR #17)

- Source: https://github.com/josephbolus/devops-as-a-service/pull/17
- Title: "Add retry with backoff to the HTTP client wrapper"
- State at capture: OPEN (captured Oct 25, 2026, ~8:35 AM MT)
- Created: 2026-10-25T08:01:20Z
- Head branch: `daas/add-retry-with-backoff-to-the-http-clien`
- Changed files: 2 (+90 / −6) — `app/http_client.py` (in the demo repo)
  and a new regression test file.
- How it was produced: a live run of the agent pipeline
  (`run_pr.py`) with all model calls served by the Meta Model API
  through the custom.meta-model-api connector (no env key). Triage,
  planner, coder, and reviewer each returned structured JSON; the
  reviewer approved; discovered tests grew 6 → 9, which the pipeline's
  live-coverage guard requires before a run can pass.
- `pr_body.md` is the PR body verbatim (`gh pr view 17 --json body`);
  `diff.patch` is `gh pr diff 17` verbatim; `pr.json` is the
  `gh pr view 17` metadata at capture.
- Note: this PR was opened earlier on Oct 25 (before the maximizer
  loop's live-eval iteration) and was captured into the scorecard on
  Oct 25 during that iteration; its wall-clock time was not recorded
  at creation. The timed live measurement for Tier 2 is the separate
  Oct 25 timed run recorded in `eval-scorecard/live-runs.json`
  (6 → 10 tests, 47.02s, reviewer approve).
