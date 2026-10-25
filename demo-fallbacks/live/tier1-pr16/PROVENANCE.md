# Provenance — live Tier-1 end state (PR #16)

- Source: https://github.com/josephbolus/devops-as-a-service/pull/16
- Title: "Fix off-by-one in pagination helper"
- State at capture: OPEN (captured Oct 25, 2026, ~1:55 AM MT)
- Created: 2026-10-25T07:05:06Z
- Head branch: `daas/fix-off-by-one-in-pagination-helper`
- Changed files: 2 (+21 / −1) — `app/pagination.py` (in the demo repo)
  and a new regression test file.
- How it was produced: a live run of the agent pipeline
  (`run_pr.py`) with all model calls served by the Meta Model API
  through the custom.meta-model-api connector (no env key). Triage,
  planner, coder, and reviewer each returned structured JSON; the
  reviewer approved; discovered tests grew 6 → 8, which the pipeline's
  live-coverage guard requires before a run can pass.
- `pr_body.md` is the PR body verbatim (`gh pr view 16 --json body`);
  `diff.patch` is `gh pr diff 16` verbatim; `pr.json` is the
  `gh pr view 16` metadata at capture.
- Predecessor: PR #15 (same issue) was closed as superseded after the
  reviewer caught that its regression test was an inert pytest-style
  function — that catch is why the test-count-growth guard exists.
